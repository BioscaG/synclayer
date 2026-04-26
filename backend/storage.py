"""On-disk persistence for SyncLayer.

A small JSON-backed store that survives process restarts and grows as new
sources are ingested. Designed for single-tenant deployments at the
hundreds-to-thousands-of-entities scale, not millions.

Files (under data/store/):
    entities.json        — {entity_id: Entity}
    embeddings.json      — {entity_id: [float, ...]}
    pair_cache.json      — {pair_key: {relationship, confidence, explanation}}
    conflicts.json       — last computed list[Conflict]
    events.jsonl         — append-only ingestion event log
    meta.json            — {last_meeting_analysis_at, sources: {...}}
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

from backend.models.schemas import Conflict, Entity, IngestEvent

log = logging.getLogger(__name__)

DEFAULT_ROOT = Path("data/store")


def _pair_key(id_a: str, id_b: str) -> str:
    a, b = sorted((id_a, id_b))
    return f"{a}::{b}"


class Store:
    """Process-wide persistent state."""

    def __init__(self, root: Path | str = DEFAULT_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

        self._entities: dict[str, Entity] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._pair_cache: dict[str, dict] = {}
        self._conflicts: list[Conflict] = []
        self._events: list[IngestEvent] = []
        self._meta: dict = {}

        self._load()

    # ------------------------------------------------------------------
    # Disk I/O
    # ------------------------------------------------------------------
    @property
    def _entities_path(self) -> Path:
        return self.root / "entities.json"

    @property
    def _embeddings_path(self) -> Path:
        return self.root / "embeddings.json"

    @property
    def _pair_cache_path(self) -> Path:
        return self.root / "pair_cache.json"

    @property
    def _conflicts_path(self) -> Path:
        return self.root / "conflicts.json"

    @property
    def _events_path(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def _meta_path(self) -> Path:
        return self.root / "meta.json"

    def _load(self) -> None:
        if self._entities_path.exists():
            data = json.loads(self._entities_path.read_text())
            self._entities = {k: Entity.model_validate(v) for k, v in data.items()}
        if self._embeddings_path.exists():
            self._embeddings = json.loads(self._embeddings_path.read_text())
        if self._pair_cache_path.exists():
            self._pair_cache = json.loads(self._pair_cache_path.read_text())
        if self._conflicts_path.exists():
            data = json.loads(self._conflicts_path.read_text())
            self._conflicts = [Conflict.model_validate(c) for c in data]
        if self._meta_path.exists():
            self._meta = json.loads(self._meta_path.read_text())
        if self._events_path.exists():
            for line in self._events_path.read_text().splitlines():
                if line.strip():
                    self._events.append(IngestEvent.model_validate_json(line))
        log.info(
            "Loaded store: %d entities, %d cached pairs, %d conflicts, %d events",
            len(self._entities),
            len(self._pair_cache),
            len(self._conflicts),
            len(self._events),
        )

    def save(self) -> None:
        with self._lock:
            self._entities_path.write_text(
                json.dumps(
                    {k: v.model_dump(mode="json") for k, v in self._entities.items()},
                    indent=0,
                )
            )
            self._embeddings_path.write_text(json.dumps(self._embeddings))
            self._pair_cache_path.write_text(json.dumps(self._pair_cache, indent=0))
            self._conflicts_path.write_text(
                json.dumps(
                    [c.model_dump(mode="json") for c in self._conflicts], indent=0
                )
            )
            self._meta_path.write_text(json.dumps(self._meta, indent=2))
            # events.jsonl is appended on the fly in record_event

    # ------------------------------------------------------------------
    # Entities + embeddings
    # ------------------------------------------------------------------
    def add_entities(
        self, entities: Iterable[Entity], embeddings: Iterable[list[float]]
    ) -> int:
        """Insert new entities and their embeddings. Returns # newly added."""
        added = 0
        with self._lock:
            for ent, emb in zip(entities, embeddings):
                if ent.id in self._entities:
                    continue
                self._entities[ent.id] = ent
                self._embeddings[ent.id] = list(emb)
                added += 1
        return added

    def all_entities(self) -> list[Entity]:
        return list(self._entities.values())

    def all_embeddings_matrix(self) -> tuple[list[Entity], np.ndarray]:
        ents = list(self._entities.values())
        if not ents:
            return [], np.empty((0, 0), dtype=np.float32)
        mat = np.array(
            [self._embeddings[e.id] for e in ents], dtype=np.float32
        )
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return ents, mat / norms

    def entities_for_meeting(self, meeting_id: str) -> list[Entity]:
        return [
            e for e in self._entities.values()
            if e.source_type.value == "meeting" and e.source_id == meeting_id
        ]

    def entities_added_since(self, ts: Optional[datetime]) -> list[Entity]:
        if ts is None:
            return list(self._entities.values())
        return [e for e in self._entities.values() if e.timestamp > ts]

    # ------------------------------------------------------------------
    # Pair cache (Claude normalizer verdicts)
    # ------------------------------------------------------------------
    def pair_cache_get(self, id_a: str, id_b: str) -> Optional[dict]:
        return self._pair_cache.get(_pair_key(id_a, id_b))

    def pair_cache_put(self, id_a: str, id_b: str, value: dict) -> None:
        with self._lock:
            self._pair_cache[_pair_key(id_a, id_b)] = value

    def pair_cache_size(self) -> int:
        return len(self._pair_cache)

    # ------------------------------------------------------------------
    # Conflicts
    # ------------------------------------------------------------------
    def set_conflicts(self, conflicts: list[Conflict]) -> None:
        with self._lock:
            self._conflicts = list(conflicts)

    def all_conflicts(self) -> list[Conflict]:
        return list(self._conflicts)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def record_event(self, event: IngestEvent) -> None:
        with self._lock:
            self._events.insert(0, event)
            self._events = self._events[:200]
            with self._events_path.open("a") as f:
                f.write(event.model_dump_json() + "\n")

    def recent_events(self, limit: int = 50) -> list[IngestEvent]:
        return list(self._events[:limit])

    def prune_orphan_events(self) -> int:
        """Drop events whose team is no longer present (config + entities).

        Used to clean up the activity feed when a team was removed before
        cascade-event-cleanup existed. Idempotent — returns # of events
        removed.
        """
        cfg = self.company_config()
        registered = set((cfg.get("teams") or {}).keys())
        in_entities = {e.team for e in self._entities.values() if e.team}
        keep = registered | in_entities
        with self._lock:
            before = len(self._events)
            self._events = [e for e in self._events if e.team in keep]
            removed = before - len(self._events)
            if removed and self._events_path.exists():
                if self._events:
                    self._events_path.write_text(
                        "\n".join(e.model_dump_json() for e in self._events) + "\n"
                    )
                else:
                    self._events_path.unlink()
        return removed

    # ------------------------------------------------------------------
    # Meta (timestamps, source bookkeeping)
    # ------------------------------------------------------------------
    def set_last_meeting_analysis(self, ts: datetime) -> None:
        with self._lock:
            self._meta["last_meeting_analysis_at"] = ts.isoformat()

    def last_meeting_analysis(self) -> Optional[datetime]:
        v = self._meta.get("last_meeting_analysis_at")
        return datetime.fromisoformat(v) if v else None

    # ------------------------------------------------------------------
    # Conflict history (one snapshot per analysis run, used by the dashboard)
    # ------------------------------------------------------------------
    def append_conflict_snapshot(self, snapshot: dict) -> None:
        """Append a {at, total, critical, by_type, by_severity} record."""
        with self._lock:
            history = self._meta.setdefault("conflict_history", [])
            history.append(snapshot)
            # Keep the last 200 snapshots — way more than any demo needs.
            if len(history) > 200:
                self._meta["conflict_history"] = history[-200:]

    def conflict_history(self) -> list[dict]:
        return list(self._meta.get("conflict_history", []))

    def mark_source_seen(self, source_type: str, source_id: str) -> None:
        with self._lock:
            sources = self._meta.setdefault("sources", {})
            sources[f"{source_type}:{source_id}"] = datetime.utcnow().isoformat()

    # ------------------------------------------------------------------
    # Company configuration (teams + their connected sources)
    # ------------------------------------------------------------------
    def company_config(self) -> dict:
        """Return the persisted company config or a sensible default."""
        return self._meta.get(
            "company",
            {
                "name": "My Company",
                "teams": {},  # team_name -> {"repos":[], "slack_channels":[], "ticket_paths":[], "color":"#…"}
            },
        )

    def set_company_config(self, config: dict) -> None:
        with self._lock:
            self._meta["company"] = config

    def upsert_team(self, name: str, **fields) -> None:
        with self._lock:
            cfg = self._meta.setdefault(
                "company", {"name": "My Company", "teams": {}}
            )
            team = cfg["teams"].setdefault(
                name,
                {"repos": [], "slack_channels": [], "ticket_paths": [], "color": ""},
            )
            for k, v in fields.items():
                team[k] = v

    def remove_team(self, name: str) -> None:
        with self._lock:
            cfg = self._meta.get("company", {})
            cfg.get("teams", {}).pop(name, None)

    def forget_team_data(self, team: str) -> int:
        """Wipe every trace of ``team``: entities, embeddings, conflicts,
        per-source sync state, and the activity event log. Returns how many
        entities were removed.

        Used both by ``DELETE /config/team/{name}`` (cascade on team removal)
        and the orphan-cleanup flow.
        """
        with self._lock:
            ids = [eid for eid, ent in self._entities.items() if ent.team == team]
            for eid in ids:
                self._entities.pop(eid, None)
                self._embeddings.pop(eid, None)
            self._conflicts = [
                c
                for c in self._conflicts
                if c.entity_a.team != team and c.entity_b.team != team
            ]
            states = self._meta.get("source_state", {})
            for key in list(states.keys()):
                # source_state keys are formatted "<kind>::<team>::<source_id>"
                if f"::{team}::" in key:
                    states.pop(key, None)
            # Activity log: drop events for this team and rewrite the file so
            # the cleanup survives a process restart. events.jsonl is otherwise
            # append-only.
            self._events = [e for e in self._events if e.team != team]
            if self._events_path.exists():
                if self._events:
                    self._events_path.write_text(
                        "\n".join(e.model_dump_json() for e in self._events) + "\n"
                    )
                else:
                    self._events_path.unlink()
        return len(ids)

    # ------------------------------------------------------------------
    # Per-source sync state (baseline + incremental tracking)
    # ------------------------------------------------------------------
    def source_state(self, kind: str, team: str, source_id: str) -> dict:
        """Return the persisted sync state for a given source, or a default."""
        key = f"{kind}::{team}::{source_id}"
        states = self._meta.get("source_state", {})
        return states.get(
            key,
            {
                "initialized": False,
                "last_synced_at": None,
                "seen_pr_numbers": [],
                "seen_commit_shas": [],
                "seen_message_ts": [],
                "entity_count": 0,
            },
        )

    def set_source_state(
        self, kind: str, team: str, source_id: str, state: dict
    ) -> None:
        with self._lock:
            states = self._meta.setdefault("source_state", {})
            states[f"{kind}::{team}::{source_id}"] = state

    def all_source_states(self) -> dict[str, dict]:
        return dict(self._meta.get("source_state", {}))

    def entities_from_source(self, source_id: str) -> list[Entity]:
        return [e for e in self._entities.values() if e.source_id == source_id]

    def pending_non_meeting_sources(self) -> int:
        """How many entities arrived since the last meeting analysis (and are not from a meeting)."""
        last = self.last_meeting_analysis()
        return sum(
            1
            for e in self._entities.values()
            if e.source_type.value != "meeting"
            and (last is None or e.timestamp > last)
        )

    def stats(self) -> dict:
        from collections import Counter

        by_source = Counter(e.source_type.value for e in self._entities.values())
        by_team = Counter(e.team for e in self._entities.values())
        return {
            "entities": len(self._entities),
            "by_source": dict(by_source),
            "by_team": dict(by_team),
            "pair_cache": len(self._pair_cache),
            "conflicts": len(self._conflicts),
            "last_meeting_analysis_at": self._meta.get("last_meeting_analysis_at"),
            "pending_non_meeting_entities": self.pending_non_meeting_sources(),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------
    def reset(self) -> None:
        with self._lock:
            self._entities.clear()
            self._embeddings.clear()
            self._pair_cache.clear()
            self._conflicts.clear()
            self._events.clear()
            self._meta = {}
            for p in (
                self._entities_path,
                self._embeddings_path,
                self._pair_cache_path,
                self._conflicts_path,
                self._events_path,
                self._meta_path,
            ):
                if p.exists():
                    p.unlink()


# ---------------------------------------------------------------------------
# Per-workspace registry of Store instances
# ---------------------------------------------------------------------------
_stores: dict[str, Store] = {}


def get_store(workspace_id: str) -> Store:
    """Return the Store for a workspace, instantiating + caching if needed.

    Raises ``KeyError`` if the workspace doesn't exist in the registry.
    """
    if workspace_id in _stores:
        return _stores[workspace_id]
    from backend.workspaces import get_registry

    ws = get_registry().get(workspace_id)
    if ws is None:
        raise KeyError(f"workspace {workspace_id!r} not found")
    _stores[workspace_id] = Store(get_registry().store_root_for(workspace_id))
    return _stores[workspace_id]


def drop_store(workspace_id: str) -> None:
    """Forget the cached Store for a workspace (after deletion)."""
    _stores.pop(workspace_id, None)
