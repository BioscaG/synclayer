"""SyncLayer FastAPI app.

Multi-workspace tenant model:

- The platform hosts any number of workspaces (companies / orgs). Each one
  has its own teams, entities, embeddings, conflicts and source state,
  isolated under ``data/store/<workspace_id>/``.
- Every per-workspace endpoint is mounted under ``/w/{ws_id}/...``. Workspace
  CRUD lives at the root ``/workspaces``.
- Repos / Slack / tickets feed memory silently. Meetings are the natural
  checkpoint that re-runs cross-team conflict analysis and surfaces results.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from backend.config import POLL_INTERVAL_SECONDS
from backend.detection.conflict import classify_conflicts
from backend.extractors.meeting import process_meeting
from backend.extractors.tickets import extract_entities_from_tickets
from backend.insights import (
    all_teams,
    internal_duplications_for_team,
    team_active_work,
    team_concerns,
    team_conflicts,
    team_dependencies,
    team_entities,
    team_summary,
)
from backend.models.schemas import (
    Conflict,
    Entity,
    EntityEmbedding,
    IngestEvent,
    SourceType,
)
from backend.bots import BotPipeline, get_bot_registry, run_bot_pipeline
from backend.poller import get_poller
from backend.recall import RecallClient, RecallError
from backend import slack_oauth
from backend.semantic.embeddings import SemanticIndex, embed_entities
from backend.semantic.normalizer import normalize_pairs
from backend.storage import Store, drop_store, get_store
from backend.sync import (
    normalize_github_target,
    sync_repo,
    sync_slack_channel,
    sync_ticket_file,
)
from backend.workspaces import Workspace, get_registry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan: legacy migration + bootstrap default workspace + start poller
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    _migrate_legacy_layout()
    registry = get_registry()
    if not registry.list():
        registry.create("Default", color="#5E6AD2")
    # Normalize repo targets and clean up orphan events across every
    # workspace (one-shot idempotent fixes).
    for ws in registry.list():
        try:
            store = get_store(ws.id)
            _migrate_repo_targets(store)
            removed = store.prune_orphan_events()
            if removed:
                log.info("Pruned %d orphan event(s) from workspace %s", removed, ws.id)
        except Exception as exc:  # noqa: BLE001
            log.warning("Workspace migration failed for %s: %s", ws.id, exc)

    poller = get_poller()
    if POLL_INTERVAL_SECONDS > 0:
        await poller.start()
    try:
        yield
    finally:
        await poller.stop()


def _migrate_legacy_layout() -> None:
    """Move pre-workspace flat data (``data/store/*.json``) into a default
    workspace folder. Idempotent: if the registry already exists, no-op.
    """
    registry_path = Path("data/workspaces.json")
    legacy_marker = Path("data/store/entities.json")
    if registry_path.exists() or not legacy_marker.exists():
        return

    log.info("Detected legacy single-tenant layout — migrating to workspaces")
    registry = get_registry()
    ws = registry.create("Default", color="#5E6AD2")
    legacy_files = [
        "entities.json",
        "embeddings.json",
        "pair_cache.json",
        "conflicts.json",
        "events.jsonl",
        "meta.json",
    ]
    for fname in legacy_files:
        src = Path("data/store") / fname
        dst = registry.store_root_for(ws.id) / fname
        if src.exists():
            shutil.move(str(src), str(dst))
    log.info("Migrated legacy data into workspace %s", ws.id)


def _migrate_repo_targets(store: Store) -> None:
    """Canonicalize any github URLs already stored in team configs."""
    cfg = store.company_config()
    teams = cfg.get("teams") or {}
    changed = False
    for name, t in teams.items():
        repos = t.get("repos") or []
        normalized = [normalize_github_target(r) for r in repos]
        if normalized != repos:
            t["repos"] = normalized
            changed = True
    if changed:
        store.set_company_config(cfg)
        store.save()


app = FastAPI(title="SyncLayer", version="0.4.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Workspace dependency
# ---------------------------------------------------------------------------
def workspace_store(ws_id: str) -> Store:
    """FastAPI dependency: resolve a workspace from the URL path → its Store.

    Raises 404 if the workspace doesn't exist.
    """
    try:
        return get_store(ws_id)
    except KeyError as exc:
        raise HTTPException(404, f"workspace {ws_id} not found") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _record_event(
    store: Store, source_type: SourceType, team: str, description: str, count: int
) -> IngestEvent:
    event = IngestEvent(
        id=f"ev-{uuid.uuid4().hex[:8]}",
        source_type=source_type,
        team=team,
        description=description,
        entities_extracted=count,
        timestamp=datetime.utcnow(),
    )
    store.record_event(event)
    return event


def _embed_and_store(store: Store, entities: list[Entity]) -> int:
    if not entities:
        return 0
    embeddings = embed_entities(entities)
    return store.add_entities(
        [e.entity for e in embeddings],
        [e.embedding for e in embeddings],
    )


def _conflict_key(c: Conflict) -> tuple[str, str, str]:
    a, b = sorted((c.entity_a.id, c.entity_b.id))
    return (a, b, c.conflict_type.value)


def _run_full_analysis(store: Store) -> tuple[dict, list[Conflict]]:
    """Recompute matches → normalize (cached) → classify → snapshot. Persist."""
    entities, _matrix = store.all_embeddings_matrix()
    if len(entities) < 2:
        return (
            {"entities": len(entities), "matches": 0, "conflicts": 0, "critical": 0},
            [],
        )

    prev_keys = {_conflict_key(c) for c in store.all_conflicts()}

    embeddings = [
        EntityEmbedding(entity=e, embedding=store._embeddings[e.id])  # noqa: SLF001
        for e in entities
    ]
    index = SemanticIndex(embeddings)
    matches = index.find_cross_team_matches()

    normalized = normalize_pairs(
        matches,
        cache_get=store.pair_cache_get,
        cache_put=store.pair_cache_put,
    )
    conflicts = classify_conflicts(normalized)
    store.set_conflicts(conflicts)
    store.set_last_meeting_analysis(datetime.utcnow())
    store.save()

    by_type: dict[str, int] = {}
    critical = 0
    for c in conflicts:
        by_type[c.conflict_type.value] = by_type.get(c.conflict_type.value, 0) + 1
        if c.severity.value == "critical":
            critical += 1

    new_conflicts = [c for c in conflicts if _conflict_key(c) not in prev_keys]

    by_severity: dict[str, int] = {}
    for c in conflicts:
        by_severity[c.severity.value] = by_severity.get(c.severity.value, 0) + 1
    store.append_conflict_snapshot(
        {
            "at": datetime.utcnow().isoformat(),
            "total": len(conflicts),
            "critical": critical,
            "by_type": by_type,
            "by_severity": by_severity,
            "entities": len(entities),
        }
    )

    summary = {
        "entities": len(entities),
        "matches": len(matches),
        "conflicts": len(conflicts),
        "critical": critical,
        "by_type": by_type,
        "new_conflicts": len(new_conflicts),
    }
    return summary, new_conflicts


def _record_source_error(
    store: Store, kind: str, team: str, source_id: str, err: str
) -> None:
    state = store.source_state(kind, team, source_id)
    state["last_error"] = err[:500]
    state["last_attempt_at"] = datetime.utcnow().isoformat()
    store.set_source_state(kind, team, source_id, state)
    store.save()


def _safe_sync_repo(store: Store, team: str, target: str) -> None:
    try:
        sync_repo(team, target, store=store)
    except Exception as exc:  # noqa: BLE001
        log.warning("Auto-sync of repo %s@%s failed: %s", target, team, exc)
        _record_source_error(store, "repo", team, target, str(exc))


def _safe_sync_slack(store: Store, team: str, target: str) -> None:
    try:
        sync_slack_channel(team, target, store=store)
    except Exception as exc:  # noqa: BLE001
        log.warning("Auto-sync of slack %s@%s failed: %s", target, team, exc)
        _record_source_error(store, "slack", team, target, str(exc))


def _safe_sync_ticket(store: Store, team: str, target: str) -> None:
    try:
        sync_ticket_file(team, target, store=store)
    except Exception as exc:  # noqa: BLE001
        log.warning("Auto-sync of ticket %s@%s failed: %s", target, team, exc)
        _record_source_error(store, "ticket", team, target, str(exc))


def _sync_team_sources(store: Store, name: str, t_cfg: dict) -> list[dict]:
    summary: list[dict] = []
    for repo in t_cfg.get("repos", []) or []:
        try:
            r = sync_repo(name, repo, store=store)
            summary.append({"kind": "repo", "target": repo, **r})
        except Exception as exc:  # noqa: BLE001
            _record_source_error(store, "repo", name, repo, str(exc))
            summary.append({"kind": "repo", "target": repo, "error": str(exc)})
    for ch in t_cfg.get("slack_channels", []) or []:
        try:
            r = sync_slack_channel(name, ch, store=store)
            summary.append({"kind": "slack", "target": ch, **r})
        except Exception as exc:  # noqa: BLE001
            _record_source_error(store, "slack", name, ch, str(exc))
            summary.append({"kind": "slack", "target": ch, "error": str(exc)})
    for tk in t_cfg.get("ticket_paths", []) or []:
        try:
            r = sync_ticket_file(name, tk, store=store)
            summary.append({"kind": "ticket", "target": tk, **r})
        except Exception as exc:  # noqa: BLE001
            _record_source_error(store, "ticket", name, tk, str(exc))
            summary.append({"kind": "ticket", "target": tk, "error": str(exc)})
    return summary


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class IngestRepoRequest(BaseModel):
    team: str
    repo_full_name: Optional[str] = None
    json_path: Optional[str] = None


class IngestSlackRequest(BaseModel):
    team: str
    channel_id: Optional[str] = None
    json_path: Optional[str] = None


class IngestResponse(BaseModel):
    entities_extracted: int
    new_in_memory: int
    triggered_analysis: bool = False
    analysis: Optional[dict] = None
    new_conflicts: list[Conflict] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    entities: int
    matches: int
    conflicts: int
    critical: int
    by_type: dict[str, int] = Field(default_factory=dict)


class TeamConfig(BaseModel):
    color: str = ""
    repos: list[str] = Field(default_factory=list)
    slack_channels: list[str] = Field(default_factory=list)
    ticket_paths: list[str] = Field(default_factory=list)


class CompanyConfig(BaseModel):
    name: str
    teams: dict[str, TeamConfig] = Field(default_factory=dict)


class TeamUpsertRequest(BaseModel):
    name: str
    color: Optional[str] = None
    repos: Optional[list[str]] = None
    slack_channels: Optional[list[str]] = None
    ticket_paths: Optional[list[str]] = None


class WorkspaceCreateRequest(BaseModel):
    name: str
    color: str = "#5E6AD2"


class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class WorkspaceSummary(BaseModel):
    id: str
    name: str
    color: str
    created_at: datetime
    entities: int
    teams: int
    conflicts: int
    critical_conflicts: int


# ===========================================================================
# Workspace registry endpoints (no /w prefix)
# ===========================================================================
@app.get("/")
def root():
    """Root health check + workspace count."""
    return {
        "service": "SyncLayer",
        "status": "ok",
        "workspaces": len(get_registry().list()),
    }


@app.get("/workspaces")
def list_workspaces() -> list[WorkspaceSummary]:
    out: list[WorkspaceSummary] = []
    for ws in get_registry().list():
        store = get_store(ws.id)
        s = store.stats()
        confs = store.all_conflicts()
        critical = sum(1 for c in confs if c.severity.value == "critical")
        out.append(
            WorkspaceSummary(
                id=ws.id,
                name=ws.name,
                color=ws.color,
                created_at=ws.created_at,
                entities=s["entities"],
                teams=len(s["by_team"]),
                conflicts=s["conflicts"],
                critical_conflicts=critical,
            )
        )
    return out


@app.post("/workspaces", response_model=Workspace)
def create_workspace(req: WorkspaceCreateRequest):
    if not req.name.strip():
        raise HTTPException(400, "name is required")
    return get_registry().create(req.name, req.color)


@app.get("/workspaces/{ws_id}", response_model=Workspace)
def get_workspace(ws_id: str):
    ws = get_registry().get(ws_id)
    if ws is None:
        raise HTTPException(404, f"workspace {ws_id} not found")
    return ws


@app.patch("/workspaces/{ws_id}", response_model=Workspace)
def update_workspace(ws_id: str, req: WorkspaceUpdateRequest):
    ws = get_registry().update(ws_id, name=req.name, color=req.color)
    if ws is None:
        raise HTTPException(404, f"workspace {ws_id} not found")
    return ws


@app.delete("/workspaces/{ws_id}")
def delete_workspace(ws_id: str):
    if not get_registry().delete(ws_id):
        raise HTTPException(404, f"workspace {ws_id} not found")
    drop_store(ws_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Slack OAuth (root-level, not under /w because the redirect URI is fixed)
# ---------------------------------------------------------------------------
def _frontend_origin() -> str:
    """Best-effort guess at the frontend URL — derived from the Slack redirect
    URI which the user configured already (e.g. ``http://localhost:3000``)."""
    uri = slack_oauth.SLACK_REDIRECT_URI
    if "://" in uri:
        scheme, rest = uri.split("://", 1)
        host = rest.split("/", 1)[0]
        return f"{scheme}://{host}"
    return ""


@app.get("/slack/oauth/start")
def slack_oauth_start(ws_id: str):
    if not slack_oauth.is_configured():
        raise HTTPException(
            500,
            "Slack OAuth is not configured. Set SLACK_CLIENT_ID and "
            "SLACK_CLIENT_SECRET in your .env, then restart the backend.",
        )
    if get_registry().get(ws_id) is None:
        raise HTTPException(404, f"workspace {ws_id} not found")
    return RedirectResponse(slack_oauth.authorize_url(state=ws_id))


@app.get("/slack/oauth/callback")
def slack_oauth_callback(code: str, state: str):
    ws_id = state
    if get_registry().get(ws_id) is None:
        raise HTTPException(400, "invalid state (workspace gone)")

    try:
        data = slack_oauth.exchange_code(code)
    except slack_oauth.SlackOAuthError as exc:
        raise HTTPException(502, str(exc)) from exc

    bot_token = data.get("access_token")
    team = data.get("team") or {}
    if not bot_token:
        raise HTTPException(502, "Slack returned no access_token")

    store = get_store(ws_id)
    store._meta["slack"] = {  # noqa: SLF001
        "bot_token": bot_token,
        "team_id": team.get("id"),
        "team_name": team.get("name"),
        "bot_user_id": data.get("bot_user_id"),
        "scope": data.get("scope"),
        "connected_at": datetime.utcnow().isoformat(),
    }
    store.save()
    log.info(
        "Slack connected for workspace %s → Slack team %s (%s)",
        ws_id, team.get("name"), team.get("id"),
    )

    origin = _frontend_origin() or ""
    return RedirectResponse(f"{origin}/w/{ws_id}/setup?slack=connected")


@app.get("/w/{ws_id}/slack/status")
def slack_status(store: Store = Depends(workspace_store)):
    cfg = store._meta.get("slack") or {}  # noqa: SLF001
    if cfg.get("bot_token"):
        return {
            "connected": True,
            "team_id": cfg.get("team_id"),
            "team_name": cfg.get("team_name"),
            "connected_at": cfg.get("connected_at"),
            "configured": slack_oauth.is_configured(),
        }
    return {"connected": False, "configured": slack_oauth.is_configured()}


@app.get("/w/{ws_id}/slack/channels")
def slack_channels(store: Store = Depends(workspace_store)):
    cfg = store._meta.get("slack") or {}  # noqa: SLF001
    token = cfg.get("bot_token")
    if not token:
        raise HTTPException(400, "Slack not connected to this workspace")
    try:
        return slack_oauth.list_channels(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Slack API: {exc}") from exc


@app.post("/w/{ws_id}/slack/disconnect")
def slack_disconnect(ws_id: str, store: Store = Depends(workspace_store)):
    cfg = store._meta.get("slack") or {}  # noqa: SLF001
    token = cfg.get("bot_token")
    if token:
        slack_oauth.revoke_token(token)
    store._meta.pop("slack", None)  # noqa: SLF001
    store.save()
    log.info("Slack disconnected from workspace %s", ws_id)
    return {"ok": True}


# ===========================================================================
# Per-workspace endpoints — every route is mounted under /w/{ws_id}/...
# ===========================================================================

# ---------------------------------------------------------------------------
# Health / state
# ---------------------------------------------------------------------------
@app.get("/w/{ws_id}/stats")
def stats(store: Store = Depends(workspace_store)):
    return store.stats()


@app.post("/w/{ws_id}/reset")
def reset(store: Store = Depends(workspace_store)):
    store.reset()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Ingestion (silent)
# ---------------------------------------------------------------------------
@app.post("/w/{ws_id}/ingest/repo", response_model=IngestResponse)
def ingest_repo(req: IngestRepoRequest, store: Store = Depends(workspace_store)):
    if not req.repo_full_name and not req.json_path:
        raise HTTPException(400, "Provide repo_full_name or json_path")
    target = req.repo_full_name or req.json_path  # type: ignore[assignment]
    result = sync_repo(req.team, target, store=store)
    return IngestResponse(
        entities_extracted=result["extracted_entities"],
        new_in_memory=result["new_entities"],
        triggered_analysis=False,
        analysis={"mode": result["mode"], "new_pr_numbers": result["new_pr_numbers"]},
    )


@app.post("/w/{ws_id}/ingest/slack", response_model=IngestResponse)
def ingest_slack(req: IngestSlackRequest, store: Store = Depends(workspace_store)):
    if not req.channel_id and not req.json_path:
        raise HTTPException(400, "Provide channel_id or json_path")
    target = req.channel_id or req.json_path  # type: ignore[assignment]
    result = sync_slack_channel(req.team, target, store=store)
    return IngestResponse(
        entities_extracted=result["extracted_entities"],
        new_in_memory=result["new_entities"],
        triggered_analysis=False,
    )


@app.post("/w/{ws_id}/ingest/tickets", response_model=IngestResponse)
async def ingest_tickets(
    team: str = Form(...),
    file: Optional[UploadFile] = File(None),
    json_path: Optional[str] = Form(None),
    store: Store = Depends(workspace_store),
):
    if file is None and not json_path:
        raise HTTPException(400, "Upload a JSON file or provide json_path")

    if file is not None:
        contents = await file.read()
        try:
            tickets = json.loads(contents)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"Invalid JSON: {exc}") from exc
        source_id = file.filename or "uploaded"
        entities = extract_entities_from_tickets(tickets, team, source_id)
        new = _embed_and_store(store, entities)
        _record_event(store, SourceType.TICKET, team, "Tickets ingested", len(entities))
        store.save()
        return IngestResponse(
            entities_extracted=len(entities),
            new_in_memory=new,
            triggered_analysis=False,
        )

    result = sync_ticket_file(team, json_path, store=store)  # type: ignore[arg-type]
    return IngestResponse(
        entities_extracted=result["extracted_entities"],
        new_in_memory=result["new_entities"],
        triggered_analysis=False,
    )


# ---------------------------------------------------------------------------
# Meeting ingestion (triggers analysis)
# ---------------------------------------------------------------------------
@app.post("/w/{ws_id}/ingest/meeting", response_model=IngestResponse)
async def ingest_meeting(
    team: str = Form(...),
    meeting_id: Optional[str] = Form(None),
    transcript_text: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None),
    skip_analysis: bool = Form(False),
    store: Store = Depends(workspace_store),
):
    if not transcript_text and not audio:
        raise HTTPException(400, "Provide transcript_text or an audio file")

    meeting_id = meeting_id or f"meeting-{uuid.uuid4().hex[:6]}"
    audio_path: Optional[str] = None
    try:
        if audio is not None:
            suffix = os.path.splitext(audio.filename or "")[1] or ".mp3"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(await audio.read())
            tmp.close()
            audio_path = tmp.name

        entities = process_meeting(
            audio_path=audio_path,
            transcript_text=transcript_text,
            team=team,
            meeting_id=meeting_id,
        )
    finally:
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)

    new = _embed_and_store(store, entities)
    _record_event(
        store, SourceType.MEETING, team, f"Meeting '{meeting_id}' ingested", len(entities)
    )

    analysis_summary: Optional[dict] = None
    new_conflicts: list[Conflict] = []
    triggered = False
    if not skip_analysis and len(store.all_entities()) >= 2:
        analysis_summary, new_conflicts = _run_full_analysis(store)
        triggered = True
        # Scope the post-meeting banner to the team that held the meeting.
        new_conflicts = [
            c for c in new_conflicts
            if c.entity_a.team == team or c.entity_b.team == team
        ]

    store.save()
    return IngestResponse(
        entities_extracted=len(entities),
        new_in_memory=new,
        triggered_analysis=triggered,
        analysis=analysis_summary,
        new_conflicts=new_conflicts,
    )


# ---------------------------------------------------------------------------
# Live-API sync helpers
# ---------------------------------------------------------------------------
@app.post("/w/{ws_id}/sync/github/{owner}/{repo}", response_model=IngestResponse)
def sync_github(
    owner: str, repo: str, team: str, store: Store = Depends(workspace_store)
):
    full_name = f"{owner}/{repo}"
    result = sync_repo(team, full_name, store=store)
    return IngestResponse(
        entities_extracted=result["extracted_entities"],
        new_in_memory=result["new_entities"],
        triggered_analysis=False,
        analysis={"mode": result["mode"], "new_pr_numbers": result["new_pr_numbers"]},
    )


@app.post("/w/{ws_id}/sync/slack/{channel_id}", response_model=IngestResponse)
def sync_slack(
    channel_id: str, team: str, store: Store = Depends(workspace_store)
):
    result = sync_slack_channel(team, channel_id, store=store)
    return IngestResponse(
        entities_extracted=result["extracted_entities"],
        new_in_memory=result["new_entities"],
        triggered_analysis=False,
    )


# ---------------------------------------------------------------------------
# Manual analysis (escape hatch)
# ---------------------------------------------------------------------------
@app.post("/w/{ws_id}/analyze", response_model=AnalysisResponse)
def analyze(store: Store = Depends(workspace_store)):
    if len(store.all_entities()) < 2:
        raise HTTPException(400, "Need at least 2 entities to analyze")
    summary, _new = _run_full_analysis(store)
    return AnalysisResponse(
        **{k: v for k, v in summary.items() if k in AnalysisResponse.model_fields}
    )


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------
@app.get("/w/{ws_id}/entities")
def get_entities(store: Store = Depends(workspace_store)):
    return [e.model_dump(mode="json") for e in store.all_entities()]


@app.get("/w/{ws_id}/conflicts")
def get_conflicts(store: Store = Depends(workspace_store)):
    return [c.model_dump(mode="json") for c in store.all_conflicts()]


@app.get("/w/{ws_id}/events")
def get_events(store: Store = Depends(workspace_store)):
    return [e.model_dump(mode="json") for e in store.recent_events()]


# ---------------------------------------------------------------------------
# Configuration (per-workspace)
# ---------------------------------------------------------------------------
@app.get("/w/{ws_id}/config", response_model=CompanyConfig)
def get_config(store: Store = Depends(workspace_store)):
    return store.company_config()


@app.post("/w/{ws_id}/config", response_model=CompanyConfig)
def set_config(cfg: CompanyConfig, store: Store = Depends(workspace_store)):
    store.set_company_config(cfg.model_dump())
    store.save()
    return store.company_config()


@app.post("/w/{ws_id}/config/team")
def upsert_team(
    req: TeamUpsertRequest,
    background_tasks: BackgroundTasks,
    store: Store = Depends(workspace_store),
):
    cfg = store.company_config()
    prev = cfg.get("teams", {}).get(req.name, {}) or {}

    fields = {k: v for k, v in req.model_dump().items() if k != "name" and v is not None}
    if "repos" in fields:
        fields["repos"] = [normalize_github_target(r) for r in fields["repos"]]
    store.upsert_team(req.name, **fields)
    store.save()

    if "repos" in fields:
        for r in set(fields["repos"]) - set(prev.get("repos") or []):
            background_tasks.add_task(_safe_sync_repo, store, req.name, r)
    if req.slack_channels is not None:
        for s in set(req.slack_channels) - set(prev.get("slack_channels") or []):
            background_tasks.add_task(_safe_sync_slack, store, req.name, s)
    if req.ticket_paths is not None:
        for t in set(req.ticket_paths) - set(prev.get("ticket_paths") or []):
            background_tasks.add_task(_safe_sync_ticket, store, req.name, t)

    return store.company_config()


@app.delete("/w/{ws_id}/config/team/{name}")
def delete_team(name: str, store: Store = Depends(workspace_store)):
    """Remove a team and cascade-delete its data."""
    removed = store.forget_team_data(name)
    store.remove_team(name)
    store.save()
    log.info("Deleted team %s (removed %d entities)", name, removed)
    return store.company_config()


# ---------------------------------------------------------------------------
# Team detail + bulk sync
# ---------------------------------------------------------------------------
def _internal_duplications_all(store: Store) -> list[tuple[Entity, Entity, float]]:
    entities = store.all_entities()
    if len(entities) < 2:
        return []
    embeds = [
        EntityEmbedding(entity=e, embedding=store._embeddings[e.id])  # noqa: SLF001
        for e in entities
    ]
    return SemanticIndex(embeds).find_internal_duplications()


@app.get("/w/{ws_id}/teams")
def list_teams(store: Store = Depends(workspace_store)):
    cfg = store.company_config()
    entities = store.all_entities()
    conflicts = store.all_conflicts()
    names = all_teams(entities, list(cfg.get("teams", {}).keys()))
    return [
        {
            **team_summary(t, entities, conflicts),
            "config": cfg.get("teams", {}).get(t, {}),
        }
        for t in names
    ]


# IMPORTANT: declare /teams/orphans before /teams/{name}.
@app.get("/w/{ws_id}/teams/orphans")
def orphan_teams(store: Store = Depends(workspace_store)):
    cfg = store.company_config()
    registered = set(cfg.get("teams", {}).keys())
    counts: dict[str, int] = {}
    for e in store.all_entities():
        if e.team and e.team not in registered:
            counts[e.team] = counts.get(e.team, 0) + 1
    return [{"team": t, "entity_count": n} for t, n in sorted(counts.items())]


@app.get("/w/{ws_id}/teams/{name}")
def team_detail(name: str, store: Store = Depends(workspace_store)):
    cfg = store.company_config()
    entities = store.all_entities()
    conflicts = store.all_conflicts()
    t_ents = team_entities(entities, name)
    t_confs = team_conflicts(conflicts, name)
    pairs = internal_duplications_for_team(_internal_duplications_all(store), name)

    src_states: dict[str, dict] = {}
    t_cfg = cfg.get("teams", {}).get(name, {})
    for kind, key in (
        ("repo", "repos"),
        ("slack", "slack_channels"),
        ("ticket", "ticket_paths"),
    ):
        for sid in t_cfg.get(key, []) or []:
            src_states[f"{kind}::{sid}"] = store.source_state(kind, name, sid)

    return {
        "team": name,
        "summary": team_summary(name, entities, conflicts),
        "config": t_cfg,
        "active_work": [e.model_dump(mode="json") for e in team_active_work(t_ents, limit=12)],
        "concerns": [e.model_dump(mode="json") for e in team_concerns(t_ents)],
        "dependencies": [e.model_dump(mode="json") for e in team_dependencies(t_ents)],
        "entities": [e.model_dump(mode="json") for e in t_ents],
        "conflicts": [c.model_dump(mode="json") for c in t_confs],
        "internal_duplications": [
            {
                "entity_a": a.model_dump(mode="json"),
                "entity_b": b.model_dump(mode="json"),
                "similarity": float(s),
            }
            for a, b, s in pairs
        ],
        "source_states": src_states,
    }


@app.post("/w/{ws_id}/sync/team/{name}")
def sync_team(name: str, store: Store = Depends(workspace_store)):
    cfg = store.company_config()
    t_cfg = cfg.get("teams", {}).get(name)
    if not t_cfg:
        raise HTTPException(404, f"team {name} not configured")
    return {"team": name, "results": _sync_team_sources(store, name, t_cfg)}


@app.post("/w/{ws_id}/sync/all")
def sync_all(store: Store = Depends(workspace_store)):
    cfg = store.company_config()
    teams = cfg.get("teams", {}) or {}
    results: list[dict] = []
    for team_name, t_cfg in teams.items():
        try:
            results.append(
                {"team": team_name, "results": _sync_team_sources(store, team_name, t_cfg)}
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"team": team_name, "error": str(exc)})
    return {"teams": results, "synced_at": datetime.utcnow().isoformat()}


@app.get("/w/{ws_id}/sync/status")
def sync_status(store: Store = Depends(workspace_store)):
    return {
        "polling": get_poller().status(),
        "sources": store.all_source_states(),
    }


@app.delete("/w/{ws_id}/entities/by-team/{team}")
def forget_team_entities(team: str, store: Store = Depends(workspace_store)):
    removed = store.forget_team_data(team)
    store.save()
    return {"removed_entities": removed}


class MeetingFromUrlRequest(BaseModel):
    meeting_url: str
    team: str
    title: Optional[str] = None
    bot_name: str = "SyncLayer Notetaker"
    transcription_provider: str = "meeting_captions"


async def _ingest_bot_transcript(bot: BotPipeline, transcript_text: str) -> dict:
    """Callback handed to run_bot_pipeline — feeds the transcript to the
    same pipeline as a manually-uploaded meeting. Runs analysis and stores
    new entities + conflicts on the workspace's store.
    """
    store = get_store(bot.ws_id)
    meeting_id = f"recall-{bot.bot_id[:8]}"

    entities = process_meeting(
        audio_path=None,
        transcript_text=transcript_text,
        team=bot.team,
        meeting_id=meeting_id,
    )
    new_in_memory = _embed_and_store(store, entities)
    _record_event(
        store,
        SourceType.MEETING,
        bot.team,
        f"Meeting '{bot.title or meeting_id}' (Recall bot) ingested",
        len(entities),
    )

    new_conflicts: list[Conflict] = []
    if len(store.all_entities()) >= 2:
        _summary, all_new = _run_full_analysis(store)
        # Scope to the meeting's team — same logic as the manual ingest path.
        new_conflicts = [
            c for c in all_new
            if c.entity_a.team == bot.team or c.entity_b.team == bot.team
        ]
    store.save()

    return {
        "entities_extracted": len(entities),
        "new_in_memory": new_in_memory,
        "new_conflicts": len(new_conflicts),
    }


@app.post("/w/{ws_id}/meetings/from-url")
async def meeting_from_url(
    req: MeetingFromUrlRequest,
    ws_id: str,
    store: Store = Depends(workspace_store),
):
    """Send a Recall.ai bot to a meeting URL.

    The bot joins the call (Google Meet / Zoom / Teams), records, and once
    the call ends we fetch the transcript and feed it to the cross-team
    conflict pipeline. The pipeline runs as a background asyncio task; the
    UI polls ``GET /w/{ws_id}/meetings/bots`` for live status.
    """
    cfg = store.company_config()
    if req.team not in (cfg.get("teams") or {}):
        raise HTTPException(400, f"team {req.team} is not configured in this workspace")

    try:
        client = RecallClient()
    except RecallError as exc:
        raise HTTPException(500, str(exc)) from exc
    try:
        payload = client.create_bot(
            req.meeting_url,
            bot_name=req.bot_name,
            transcription_provider=req.transcription_provider,
        )
    except RecallError as exc:
        raise HTTPException(502, f"Recall.ai: {exc}") from exc

    bot_id = payload.get("id") or payload.get("bot_id")
    if not bot_id:
        raise HTTPException(502, "Recall did not return a bot id")

    bot = BotPipeline(
        bot_id=bot_id,
        ws_id=ws_id,
        team=req.team,
        meeting_url=req.meeting_url,
        title=(req.title or "").strip(),
        bot_name=req.bot_name,
    )
    get_bot_registry().add(bot)
    asyncio.create_task(run_bot_pipeline(bot, _ingest_bot_transcript))
    log.info("Dispatched Recall bot %s to %s for team %s", bot_id, req.meeting_url, req.team)
    return bot.to_dict()


@app.get("/w/{ws_id}/meetings/bots")
def list_bots(ws_id: str, store: Store = Depends(workspace_store)):
    return [b.to_dict() for b in get_bot_registry().for_workspace(ws_id)]


@app.delete("/w/{ws_id}/meetings/bots/{bot_id}")
def kick_bot(ws_id: str, bot_id: str, store: Store = Depends(workspace_store)):
    """Politely tell a Recall bot to leave its meeting and forget it."""
    bot = get_bot_registry().get(bot_id)
    if bot is None or bot.ws_id != ws_id:
        raise HTTPException(404, "bot not found in this workspace")
    try:
        RecallClient().leave_call(bot_id)
    except RecallError as exc:
        log.warning("Recall leave_call failed for %s: %s", bot_id, exc)
    bot.status = "failed"
    bot.error = bot.error or "Kicked by user"
    bot.completed_at = datetime.utcnow()
    return {"ok": True}


@app.get("/w/{ws_id}/meetings")
def list_meetings(store: Store = Depends(workspace_store)):
    by_meeting: dict[str, dict] = {}
    for e in store.all_entities():
        if e.source_type != SourceType.MEETING:
            continue
        m = by_meeting.setdefault(
            e.source_id,
            {
                "meeting_id": e.source_id,
                "team": e.team,
                "ingested_at": e.timestamp.isoformat(),
                "entity_count": 0,
            },
        )
        m["entity_count"] += 1
        if e.timestamp.isoformat() > m["ingested_at"]:
            m["ingested_at"] = e.timestamp.isoformat()
    return sorted(by_meeting.values(), key=lambda m: m["ingested_at"], reverse=True)


@app.get("/w/{ws_id}/internal-duplications")
def internal_dupes(store: Store = Depends(workspace_store)):
    return [
        {
            "entity_a": a.model_dump(mode="json"),
            "entity_b": b.model_dump(mode="json"),
            "similarity": float(s),
        }
        for a, b, s in _internal_duplications_all(store)
    ]


@app.get("/w/{ws_id}/history")
def get_history(days: int = 14, store: Store = Depends(workspace_store)):
    from collections import defaultdict
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)

    snaps = [
        s for s in store.conflict_history()
        if datetime.fromisoformat(s["at"]) >= cutoff
    ]

    by_day_entities: dict[str, dict[str, int]] = defaultdict(
        lambda: {"meeting": 0, "github": 0, "slack": 0, "ticket": 0}
    )
    for e in store.all_entities():
        if e.timestamp < cutoff:
            continue
        day = e.timestamp.strftime("%Y-%m-%d")
        by_day_entities[day][e.source_type.value] += 1

    by_day_events: dict[str, int] = defaultdict(int)
    for ev in store.recent_events(limit=200):
        if ev.timestamp < cutoff:
            continue
        by_day_events[ev.timestamp.strftime("%Y-%m-%d")] += 1

    daily_entities: list[dict] = []
    daily_events: list[dict] = []
    for i in range(days):
        d = (datetime.utcnow() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        daily_entities.append(
            {
                "date": d,
                **by_day_entities.get(
                    d, {"meeting": 0, "github": 0, "slack": 0, "ticket": 0}
                ),
            }
        )
        daily_events.append({"date": d, "events": by_day_events.get(d, 0)})

    return {
        "conflict_snapshots": snaps,
        "daily_entities": daily_entities,
        "daily_events": daily_events,
        "window_days": days,
    }


@app.get("/w/{ws_id}/report")
def get_report(store: Store = Depends(workspace_store)):
    return JSONResponse(
        {
            "stats": store.stats(),
            "entities": [e.model_dump(mode="json") for e in store.all_entities()],
            "conflicts": [c.model_dump(mode="json") for c in store.all_conflicts()],
            "events": [e.model_dump(mode="json") for e in store.recent_events()],
        }
    )
