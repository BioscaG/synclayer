"""SyncLayer FastAPI app.

Persistent memory + meeting-triggered conflict analysis:

- Repos / Slack / Tickets only feed the memory. They do NOT trigger conflict
  detection — the live tape just keeps growing in the background.
- Meetings are the natural checkpoint. Whenever a meeting is ingested we
  re-analyze the whole memory (with a pair cache so we don't re-pay Claude
  for already-judged relationships) and surface the resulting conflicts.

A manual /analyze endpoint exists as an escape hatch.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.chat import ChatRequest, ChatResponse, answer_chat
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
from backend.poller import get_poller
from backend.semantic.embeddings import SemanticIndex, embed_entities
from backend.semantic.normalizer import normalize_pairs
from backend.storage import Store, get_store
from backend.sync import (
    normalize_github_target,
    sync_repo,
    sync_slack_channel,
    sync_ticket_file,
)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Wake the store eagerly so the first request isn't slow.
    store = get_store()
    _migrate_repo_targets(store)
    poller = get_poller()
    if POLL_INTERVAL_SECONDS > 0:
        await poller.start()
    try:
        yield
    finally:
        await poller.stop()


def _migrate_repo_targets(store: Store) -> None:
    """Canonicalize any github URLs already stored in team configs.

    Earlier saves accepted URLs verbatim, which then 404'd through PyGithub.
    On startup we rewrite ``cfg.teams[*].repos`` so each entry is the
    ``owner/repo`` form. Idempotent — entries already in canonical form are
    untouched.
    """
    cfg = store.company_config()
    teams = cfg.get("teams") or {}
    changed = False
    for name, t in teams.items():
        repos = t.get("repos") or []
        normalized = [normalize_github_target(r) for r in repos]
        if normalized != repos:
            t["repos"] = normalized
            changed = True
            log.info("Normalized repo targets for team %s: %s", name, normalized)
    if changed:
        store.set_company_config(cfg)
        store.save()


app = FastAPI(title="SyncLayer", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    """Embed entities and add them (and their vectors) to the store."""
    if not entities:
        return 0
    embeddings = embed_entities(entities)
    return store.add_entities(
        [e.entity for e in embeddings],
        [e.embedding for e in embeddings],
    )


def _conflict_key(c: Conflict) -> tuple[str, str, str]:
    """Stable identity for a conflict across re-runs.

    Conflict.id is regenerated every analysis pass (uuid in classify_conflicts),
    so we can't compare ids — but the (a, b, type) triplet is stable as long
    as the underlying entities haven't changed.
    """
    a, b = sorted((c.entity_a.id, c.entity_b.id))
    return (a, b, c.conflict_type.value)


def _run_full_analysis(store: Store) -> tuple[dict, list[Conflict]]:
    """Recompute matches → normalize (cached) → classify → graph. Persist.

    Returns ``(summary_dict, new_conflicts)`` where ``new_conflicts`` is the
    subset of the freshly classified conflicts whose (a, b, type) triplet
    wasn't present before this run. The Setup page uses this to surface
    "what just got detected" right after a meeting ingest.
    """
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

    # Snapshot for the time-series chart in the dashboard.
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


# ---------------------------------------------------------------------------
# Health / state
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    store = get_store()
    s = store.stats()
    return {
        "service": "SyncLayer",
        "status": "ok",
        **s,
    }


@app.get("/stats")
def stats():
    return get_store().stats()


@app.post("/reset")
def reset():
    get_store().reset()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Ingestion (silent: no analysis)
# ---------------------------------------------------------------------------
@app.post("/ingest/repo", response_model=IngestResponse)
def ingest_repo(req: IngestRepoRequest):
    if not req.repo_full_name and not req.json_path:
        raise HTTPException(400, "Provide repo_full_name or json_path")
    target = req.repo_full_name or req.json_path  # type: ignore[assignment]
    result = sync_repo(req.team, target)
    return IngestResponse(
        entities_extracted=result["extracted_entities"],
        new_in_memory=result["new_entities"],
        triggered_analysis=False,
        analysis={"mode": result["mode"], "new_pr_numbers": result["new_pr_numbers"]},
    )


@app.post("/ingest/slack", response_model=IngestResponse)
def ingest_slack(req: IngestSlackRequest):
    if not req.channel_id and not req.json_path:
        raise HTTPException(400, "Provide channel_id or json_path")
    target = req.channel_id or req.json_path  # type: ignore[assignment]
    result = sync_slack_channel(req.team, target)
    return IngestResponse(
        entities_extracted=result["extracted_entities"],
        new_in_memory=result["new_entities"],
        triggered_analysis=False,
    )


@app.post("/ingest/tickets", response_model=IngestResponse)
async def ingest_tickets(
    team: str = Form(...),
    file: Optional[UploadFile] = File(None),
    json_path: Optional[str] = Form(None),
):
    if file is None and not json_path:
        raise HTTPException(400, "Upload a JSON file or provide json_path")
    store = get_store()

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

    result = sync_ticket_file(team, json_path)  # type: ignore[arg-type]
    return IngestResponse(
        entities_extracted=result["extracted_entities"],
        new_in_memory=result["new_entities"],
        triggered_analysis=False,
    )


# ---------------------------------------------------------------------------
# Meeting ingestion (triggers analysis)
# ---------------------------------------------------------------------------
@app.post("/ingest/meeting", response_model=IngestResponse)
async def ingest_meeting(
    team: str = Form(...),
    meeting_id: Optional[str] = Form(None),
    transcript_text: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None),
    skip_analysis: bool = Form(False),
):
    if not transcript_text and not audio:
        raise HTTPException(400, "Provide transcript_text or an audio file")

    store = get_store()
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
        # Scope the post-meeting banner to the team that actually held the
        # meeting — running the analysis is global, but the user who just
        # uploaded a transcript only cares about issues that involve them.
        # The /conflicts page still surfaces the full company-wide map.
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
@app.post("/sync/github/{owner}/{repo}", response_model=IngestResponse)
def sync_github(owner: str, repo: str, team: str):
    full_name = f"{owner}/{repo}"
    result = sync_repo(team, full_name)
    return IngestResponse(
        entities_extracted=result["extracted_entities"],
        new_in_memory=result["new_entities"],
        triggered_analysis=False,
        analysis={"mode": result["mode"], "new_pr_numbers": result["new_pr_numbers"]},
    )


@app.post("/sync/slack/{channel_id}", response_model=IngestResponse)
def sync_slack(channel_id: str, team: str):
    result = sync_slack_channel(team, channel_id)
    return IngestResponse(
        entities_extracted=result["extracted_entities"],
        new_in_memory=result["new_entities"],
        triggered_analysis=False,
    )


# ---------------------------------------------------------------------------
# Manual analysis (escape hatch)
# ---------------------------------------------------------------------------
@app.post("/analyze", response_model=AnalysisResponse)
def analyze():
    store = get_store()
    if len(store.all_entities()) < 2:
        raise HTTPException(400, "Need at least 2 entities to analyze")
    summary, _new = _run_full_analysis(store)
    return AnalysisResponse(**{k: v for k, v in summary.items() if k in AnalysisResponse.model_fields})


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    return answer_chat(get_store(), req)


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------
@app.get("/entities")
def get_entities():
    return [e.model_dump(mode="json") for e in get_store().all_entities()]


@app.get("/conflicts")
def get_conflicts():
    return [c.model_dump(mode="json") for c in get_store().all_conflicts()]


@app.get("/events")
def get_events():
    return [e.model_dump(mode="json") for e in get_store().recent_events()]


# ---------------------------------------------------------------------------
# Configuration endpoints (consumed by the Next.js UI)
# ---------------------------------------------------------------------------
class TeamConfig(BaseModel):
    color: str = ""
    repos: list[str] = Field(default_factory=list)
    slack_channels: list[str] = Field(default_factory=list)
    ticket_paths: list[str] = Field(default_factory=list)


class CompanyConfig(BaseModel):
    name: str
    teams: dict[str, TeamConfig] = Field(default_factory=dict)


@app.get("/config", response_model=CompanyConfig)
def get_config():
    return get_store().company_config()


@app.post("/config", response_model=CompanyConfig)
def set_config(cfg: CompanyConfig):
    store = get_store()
    store.set_company_config(cfg.model_dump())
    store.save()
    return store.company_config()


class TeamUpsertRequest(BaseModel):
    name: str
    color: Optional[str] = None
    repos: Optional[list[str]] = None
    slack_channels: Optional[list[str]] = None
    ticket_paths: Optional[list[str]] = None


def _record_source_error(kind: str, team: str, source_id: str, err: str) -> None:
    """Persist a sync failure on the source state so the UI can surface it."""
    store = get_store()
    state = store.source_state(kind, team, source_id)
    state["last_error"] = err[:500]
    state["last_attempt_at"] = datetime.utcnow().isoformat()
    store.set_source_state(kind, team, source_id, state)
    store.save()


def _safe_sync_repo(team: str, target: str) -> None:
    try:
        sync_repo(team, target)
    except Exception as exc:  # noqa: BLE001
        log.warning("Auto-sync of repo %s@%s failed: %s", target, team, exc)
        _record_source_error("repo", team, target, str(exc))


def _safe_sync_slack(team: str, target: str) -> None:
    try:
        sync_slack_channel(team, target)
    except Exception as exc:  # noqa: BLE001
        log.warning("Auto-sync of slack %s@%s failed: %s", target, team, exc)
        _record_source_error("slack", team, target, str(exc))


def _safe_sync_ticket(team: str, target: str) -> None:
    try:
        sync_ticket_file(team, target)
    except Exception as exc:  # noqa: BLE001
        log.warning("Auto-sync of ticket %s@%s failed: %s", target, team, exc)
        _record_source_error("ticket", team, target, str(exc))


@app.post("/config/team")
def upsert_team(req: TeamUpsertRequest, background_tasks: BackgroundTasks):
    store = get_store()
    cfg = store.company_config()
    prev = cfg.get("teams", {}).get(req.name, {}) or {}

    fields = {k: v for k, v in req.model_dump().items() if k != "name" and v is not None}
    # Canonicalize repo references so a github.com URL and `owner/repo` are
    # stored as the same thing — and PyGithub stops 404-ing on URL pastes.
    if "repos" in fields:
        fields["repos"] = [normalize_github_target(r) for r in fields["repos"]]
    store.upsert_team(req.name, **fields)
    store.save()

    # If this upsert added new sources, kick off baseline sync immediately
    # so the user doesn't have to click "Sync sources" right after.
    if "repos" in fields:
        for r in set(fields["repos"]) - set(prev.get("repos") or []):
            background_tasks.add_task(_safe_sync_repo, req.name, r)
    if req.slack_channels is not None:
        for s in set(req.slack_channels) - set(prev.get("slack_channels") or []):
            background_tasks.add_task(_safe_sync_slack, req.name, s)
    if req.ticket_paths is not None:
        for t in set(req.ticket_paths) - set(prev.get("ticket_paths") or []):
            background_tasks.add_task(_safe_sync_ticket, req.name, t)

    return store.company_config()


@app.delete("/config/team/{name}")
def delete_team(name: str):
    """Remove a team and cascade-delete its data.

    Wipes the team's config entry, every entity tagged with it, every
    conflict that references it, and its per-source sync state. The
    orphan-recovery flow uses ``DELETE /entities/by-team/{team}`` for the
    data-only path.
    """
    store = get_store()
    removed = store.forget_team_data(name)
    store.remove_team(name)
    store.save()
    log.info("Deleted team %s (removed %d entities)", name, removed)
    return store.company_config()


# ---------------------------------------------------------------------------
# Team detail + bulk sync
# ---------------------------------------------------------------------------
def _internal_duplications_all() -> list[tuple[Entity, Entity, float]]:
    store = get_store()
    entities = store.all_entities()
    if len(entities) < 2:
        return []
    embeds = [
        EntityEmbedding(entity=e, embedding=store._embeddings[e.id])  # noqa: SLF001
        for e in entities
    ]
    return SemanticIndex(embeds).find_internal_duplications()


@app.get("/teams")
def list_teams():
    store = get_store()
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


# IMPORTANT: declare /teams/orphans BEFORE /teams/{name} — otherwise FastAPI
# matches "orphans" as a team name and never reaches this handler.
@app.get("/teams/orphans")
def orphan_teams():
    store = get_store()
    cfg = store.company_config()
    registered = set(cfg.get("teams", {}).keys())
    counts: dict[str, int] = {}
    for e in store.all_entities():
        if e.team and e.team not in registered:
            counts[e.team] = counts.get(e.team, 0) + 1
    return [{"team": t, "entity_count": n} for t, n in sorted(counts.items())]


@app.get("/teams/{name}")
def team_detail(name: str):
    store = get_store()
    cfg = store.company_config()
    entities = store.all_entities()
    conflicts = store.all_conflicts()
    t_ents = team_entities(entities, name)
    t_confs = team_conflicts(conflicts, name)
    pairs = internal_duplications_for_team(_internal_duplications_all(), name)

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


def _sync_team_sources(name: str, t_cfg: dict) -> list[dict]:
    """Sync every configured source for one team. Used by /sync/team and /sync/all."""
    summary: list[dict] = []
    for repo in t_cfg.get("repos", []) or []:
        try:
            r = sync_repo(name, repo)
            summary.append({"kind": "repo", "target": repo, **r})
        except Exception as exc:  # noqa: BLE001
            _record_source_error("repo", name, repo, str(exc))
            summary.append({"kind": "repo", "target": repo, "error": str(exc)})
    for ch in t_cfg.get("slack_channels", []) or []:
        try:
            r = sync_slack_channel(name, ch)
            summary.append({"kind": "slack", "target": ch, **r})
        except Exception as exc:  # noqa: BLE001
            _record_source_error("slack", name, ch, str(exc))
            summary.append({"kind": "slack", "target": ch, "error": str(exc)})
    for tk in t_cfg.get("ticket_paths", []) or []:
        try:
            r = sync_ticket_file(name, tk)
            summary.append({"kind": "ticket", "target": tk, **r})
        except Exception as exc:  # noqa: BLE001
            _record_source_error("ticket", name, tk, str(exc))
            summary.append({"kind": "ticket", "target": tk, "error": str(exc)})
    return summary


@app.post("/sync/team/{name}")
def sync_team(name: str):
    store = get_store()
    cfg = store.company_config()
    t_cfg = cfg.get("teams", {}).get(name)
    if not t_cfg:
        raise HTTPException(404, f"team {name} not configured")
    return {"team": name, "results": _sync_team_sources(name, t_cfg)}


@app.post("/sync/all")
def sync_all():
    """Force-sync every configured source across every team.

    Cheap to call repeatedly: each source uses delta-sync against
    seen_pr_numbers / seen_commit_shas, so steady repos cost ~nothing.
    """
    store = get_store()
    cfg = store.company_config()
    teams = cfg.get("teams", {}) or {}
    results: list[dict] = []
    for team_name, t_cfg in teams.items():
        try:
            results.append({"team": team_name, "results": _sync_team_sources(team_name, t_cfg)})
        except Exception as exc:  # noqa: BLE001
            results.append({"team": team_name, "error": str(exc)})
    return {"teams": results, "synced_at": datetime.utcnow().isoformat()}


@app.get("/sync/status")
def sync_status():
    """Status for the live sync indicators in the UI."""
    store = get_store()
    return {
        "polling": get_poller().status(),
        "sources": store.all_source_states(),
    }


@app.delete("/entities/by-team/{team}")
def forget_team_entities(team: str):
    """Remove every entity tagged with the given team. Use to clean up orphans."""
    store = get_store()
    removed = store.forget_team_data(team)
    store.save()
    return {"removed_entities": removed}


@app.get("/meetings")
def list_meetings():
    """List every meeting ever ingested, newest first.

    A "meeting" is identified by a unique ``source_id`` among entities with
    ``source_type=meeting``. We return one row per meeting with its team,
    ingest time and entity count.
    """
    store = get_store()
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
        # Keep the latest timestamp across the entities of this meeting.
        if e.timestamp.isoformat() > m["ingested_at"]:
            m["ingested_at"] = e.timestamp.isoformat()
    return sorted(by_meeting.values(), key=lambda m: m["ingested_at"], reverse=True)


@app.get("/internal-duplications")
def internal_dupes():
    return [
        {
            "entity_a": a.model_dump(mode="json"),
            "entity_b": b.model_dump(mode="json"),
            "similarity": float(s),
        }
        for a, b, s in _internal_duplications_all()
    ]


@app.get("/history")
def get_history(days: int = 14):
    """Time-series data for the dashboard charts.

    Returns:
      conflict_snapshots: every analysis run snapshot (capped to ``days``)
      daily_entities: per-day count of new entities by source type
      daily_events: per-day total count of ingest events
    """
    from collections import defaultdict
    from datetime import timedelta

    store = get_store()
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Conflict snapshots within the window
    snaps = [
        s for s in store.conflict_history()
        if datetime.fromisoformat(s["at"]) >= cutoff
    ]

    # Daily entity buckets by source type, derived from the entity timestamps
    by_day_entities: dict[str, dict[str, int]] = defaultdict(
        lambda: {"meeting": 0, "github": 0, "slack": 0, "ticket": 0}
    )
    for e in store.all_entities():
        if e.timestamp < cutoff:
            continue
        day = e.timestamp.strftime("%Y-%m-%d")
        by_day_entities[day][e.source_type.value] += 1

    # Daily event counts
    by_day_events: dict[str, int] = defaultdict(int)
    for ev in store.recent_events(limit=200):
        if ev.timestamp < cutoff:
            continue
        by_day_events[ev.timestamp.strftime("%Y-%m-%d")] += 1

    # Fill missing days so charts don't have gaps
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


@app.get("/report")
def get_report():
    store = get_store()
    return JSONResponse(
        {
            "stats": store.stats(),
            "entities": [e.model_dump(mode="json") for e in store.all_entities()],
            "conflicts": [c.model_dump(mode="json") for c in store.all_conflicts()],
            "events": [e.model_dump(mode="json") for e in store.recent_events()],
        }
    )
