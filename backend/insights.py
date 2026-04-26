"""Per-team insight derivation from the persistent store.

These helpers don't call any LLM — they slice the existing entities/conflicts
to build the per-team workspace view in the dashboard.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, Optional

from backend.models.schemas import (
    Conflict,
    DecisionType,
    Entity,
    SourceType,
)


def team_entities(entities: Iterable[Entity], team: str) -> list[Entity]:
    return [e for e in entities if e.team == team]


def by_decision_type(entities: list[Entity]) -> dict[str, list[Entity]]:
    out: dict[str, list[Entity]] = {dt.value: [] for dt in DecisionType}
    for e in entities:
        out.setdefault(e.decision_type.value, []).append(e)
    return out


def by_source_type(entities: list[Entity]) -> dict[str, list[Entity]]:
    out: dict[str, list[Entity]] = {st.value: [] for st in SourceType}
    for e in entities:
        out.setdefault(e.source_type.value, []).append(e)
    return out


def team_active_work(entities: list[Entity], limit: int = 8) -> list[Entity]:
    """Decisions / plans / commitments — what the team is actively building."""
    active_types = {
        DecisionType.DECISION,
        DecisionType.PLAN,
        DecisionType.COMMITMENT,
    }
    items = [e for e in entities if e.decision_type in active_types]
    items.sort(key=lambda e: (-e.confidence, -e.timestamp.timestamp()))
    return items[:limit]


def team_concerns(entities: list[Entity]) -> list[Entity]:
    return [e for e in entities if e.decision_type == DecisionType.CONCERN]


def team_dependencies(entities: list[Entity]) -> list[Entity]:
    return [e for e in entities if e.decision_type == DecisionType.DEPENDENCY]


def team_conflicts(conflicts: Iterable[Conflict], team: str) -> list[Conflict]:
    return [
        c
        for c in conflicts
        if c.entity_a.team == team or c.entity_b.team == team
    ]


def team_summary(team: str, entities: Iterable[Entity], conflicts: Iterable[Conflict]) -> dict:
    ents = team_entities(entities, team)
    confs = team_conflicts(conflicts, team)
    sources = Counter(e.source_type.value for e in ents)
    by_type = Counter(e.decision_type.value for e in ents)
    critical = sum(1 for c in confs if c.severity.value == "critical")
    return {
        "team": team,
        "entities": len(ents),
        "by_source": dict(sources),
        "by_type": dict(by_type),
        "concerns": sum(1 for e in ents if e.decision_type == DecisionType.CONCERN),
        "active_work": len(team_active_work(ents, limit=999)),
        "conflicts": len(confs),
        "critical_conflicts": critical,
    }


def all_teams(entities: Iterable[Entity], registered: Optional[Iterable[str]] = None) -> list[str]:
    """Union of teams that appear in entities and the configured ones."""
    seen = {e.team for e in entities if e.team}
    if registered:
        seen.update(registered)
    return sorted(seen)


def internal_duplications_for_team(
    pairs: list[tuple[Entity, Entity, float]], team: str
) -> list[tuple[Entity, Entity, float]]:
    return [(a, b, s) for a, b, s in pairs if a.team == team and b.team == team]
