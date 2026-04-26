"""Source-aware sync orchestration.

A wrapper on top of the raw extractors that:
  - looks up the persisted per-source sync state
  - picks baseline (large initial fetch) or incremental (only unseen items)
  - embeds + stores new entities
  - updates the per-source state
  - records an ingest event

The dashboard, the FastAPI backend and `demo.py` all go through here so the
"first time vs incremental" logic lives in exactly one place.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.extractors.github_extractor import process_repo
from backend.extractors.slack_extractor import process_slack
from backend.extractors.tickets import process_tickets
from backend.models.schemas import Entity, IngestEvent, SourceType
from backend.semantic.embeddings import embed_entities
from backend.storage import Store, get_store

import uuid

log = logging.getLogger(__name__)


_GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def normalize_github_target(target: str) -> str:
    """Canonicalize a GitHub repo reference.

    Accepts ``owner/repo``, full github.com URLs (``https://github.com/o/r``,
    with or without ``.git`` / trailing slash), or a JSON snapshot path.
    Returns the canonical ``owner/repo`` for github URLs and leaves
    everything else untouched. Used so the user can paste either form in
    the UI without seeing 404s from PyGithub.
    """
    target = target.strip()
    m = _GITHUB_URL_RE.match(target)
    if m:
        return m.group(1)
    return target


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _record_event(
    store: Store,
    source_type: SourceType,
    team: str,
    description: str,
    count: int,
) -> None:
    store.record_event(
        IngestEvent(
            id=f"ev-{uuid.uuid4().hex[:8]}",
            source_type=source_type,
            team=team,
            description=description,
            entities_extracted=count,
            timestamp=datetime.utcnow(),
        )
    )


def _embed_and_add(store: Store, entities: list[Entity]) -> int:
    if not entities:
        return 0
    embeds = embed_entities(entities)
    return store.add_entities(
        [e.entity for e in embeds], [e.embedding for e in embeds]
    )


# ---------------------------------------------------------------------------
# Repos
# ---------------------------------------------------------------------------
def sync_repo(
    team: str,
    target: str,
    *,
    store: Optional[Store] = None,
    repo_root: Optional[Path] = None,
    baseline_prs: int = 30,
    baseline_commits: int = 50,
    delta_prs: int = 30,
    delta_commits: int = 50,
) -> dict:
    """Sync a single repo into the store.

    ``target`` may be:
      - ``owner/repo`` or a github.com URL → live PyGithub fetch
      - a path (absolute or relative to repo_root) to a JSON snapshot

    On the first call (baseline) we extract a wide window of PRs and commits.
    On every subsequent call we only process items whose PR number / commit
    SHA hasn't been seen before, so re-syncing a steady repo costs almost
    nothing.
    """
    store = store or get_store()
    target = normalize_github_target(target)

    # Decide whether this is a path or a github reference.
    json_path: Optional[str] = None
    repo_full_name: Optional[str] = None

    candidate = Path(target)
    if not candidate.is_absolute() and repo_root:
        candidate = repo_root / target
    if candidate.exists() and candidate.is_file() and target.endswith(".json"):
        json_path = str(candidate)
    elif "/" in target and not target.endswith(".json"):
        repo_full_name = target
    else:
        # Last resort: try as github reference; the caller will see the error.
        repo_full_name = target

    source_id = repo_full_name or json_path or target
    state = store.source_state("repo", team, source_id)
    is_baseline = not state.get("initialized")
    seen_prs = set(state.get("seen_pr_numbers", []))
    seen_shas = set(state.get("seen_commit_shas", []))

    max_prs = baseline_prs if is_baseline else delta_prs
    max_commits = baseline_commits if is_baseline else delta_commits
    exclude_prs = None if is_baseline else seen_prs
    exclude_shas = None if is_baseline else seen_shas

    entities, new_pr_nums, new_shas, repo_name, latest_activity = process_repo(
        repo_full_name=repo_full_name,
        json_path=json_path,
        team=team,
        max_prs=max_prs,
        max_commits=max_commits,
        exclude_pr_numbers=exclude_prs,
        exclude_commit_shas=exclude_shas,
    )

    new_count = _embed_and_add(store, entities)

    state["initialized"] = True
    state["last_synced_at"] = datetime.utcnow().isoformat()
    state["seen_pr_numbers"] = sorted(seen_prs | new_pr_nums)
    state["seen_commit_shas"] = sorted(seen_shas | new_shas)
    state["entity_count"] = state.get("entity_count", 0) + new_count
    state["last_error"] = None
    # Track the actual repo's last activity (commit / PR) — separate from when
    # we synced. The dashboard surfaces this so users see "repo last changed
    # 2h ago" rather than "we polled it 30s ago".
    if latest_activity:
        prev = state.get("last_activity_at")
        if not prev or latest_activity > prev:
            state["last_activity_at"] = latest_activity
    store.set_source_state("repo", team, source_id, state)

    mode = "baseline" if is_baseline else "incremental"
    desc = (
        f"{mode} sync of {repo_name}"
        if entities
        else f"{mode} sync of {repo_name} (no new items)"
    )
    _record_event(store, SourceType.GITHUB, team, desc, len(entities))
    store.save()

    log.info(
        "Repo %s · %s · +%d entities (%d new in memory) · %d PRs / %d commits seen",
        source_id,
        mode,
        len(entities),
        new_count,
        len(new_pr_nums),
        len(new_shas),
    )
    return {
        "mode": mode,
        "new_pr_numbers": sorted(new_pr_nums),
        "new_commit_shas": sorted(new_shas),
        "new_entities": new_count,
        "extracted_entities": len(entities),
        "repo_name": repo_name,
        "fresh": bool(entities),
    }


# ---------------------------------------------------------------------------
# Slack (incremental by message timestamp)
# ---------------------------------------------------------------------------
def sync_slack_channel(
    team: str,
    target: str,
    *,
    store: Optional[Store] = None,
    repo_root: Optional[Path] = None,
) -> dict:
    """Best-effort incremental Slack sync.

    For now the underlying extractor always fetches the latest N messages.
    We dedupe by message timestamp, so re-running adds only fresh messages.
    """
    store = store or get_store()

    candidate = Path(target)
    if not candidate.is_absolute() and repo_root:
        candidate = repo_root / target
    json_path: Optional[str] = None
    channel_id: Optional[str] = None
    if candidate.exists() and target.endswith(".json"):
        json_path = str(candidate)
    else:
        channel_id = target

    source_id = channel_id or json_path or target
    state = store.source_state("slack", team, source_id)
    seen_ts = set(state.get("seen_message_ts", []))

    entities = process_slack(channel_id=channel_id, json_path=json_path, team=team)

    # No raw-message-level filtering yet; the extractor groups them. We just
    # treat each ingest as additive. The pair_cache dedupes downstream cost,
    # and Store.add_entities skips duplicate IDs.
    new_count = _embed_and_add(store, entities)

    state["initialized"] = True
    state["last_synced_at"] = datetime.utcnow().isoformat()
    state["entity_count"] = state.get("entity_count", 0) + new_count
    state["seen_message_ts"] = list(seen_ts)
    state["last_error"] = None
    store.set_source_state("slack", team, source_id, state)

    _record_event(
        store,
        SourceType.SLACK,
        team,
        f"slack sync of {source_id}",
        len(entities),
    )
    store.save()
    return {
        "mode": "incremental" if state.get("initialized") else "baseline",
        "extracted_entities": len(entities),
        "new_entities": new_count,
    }


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------
def sync_ticket_file(
    team: str,
    path: str,
    *,
    store: Optional[Store] = None,
    repo_root: Optional[Path] = None,
) -> dict:
    """Sync a tickets JSON file into memory."""
    store = store or get_store()
    candidate = Path(path)
    if not candidate.is_absolute() and repo_root:
        candidate = repo_root / path
    if not candidate.exists():
        raise FileNotFoundError(f"Ticket file not found: {candidate}")

    state = store.source_state("ticket", team, str(candidate))
    entities = process_tickets(str(candidate), team)
    new_count = _embed_and_add(store, entities)

    state["initialized"] = True
    state["last_synced_at"] = datetime.utcnow().isoformat()
    state["entity_count"] = state.get("entity_count", 0) + new_count
    state["last_error"] = None
    store.set_source_state("ticket", team, str(candidate), state)

    _record_event(
        store,
        SourceType.TICKET,
        team,
        f"ticket sync of {candidate.name}",
        len(entities),
    )
    store.save()
    return {
        "extracted_entities": len(entities),
        "new_entities": new_count,
    }
