"""Convert normalized entity pairs into typed Conflict objects."""
from __future__ import annotations

import logging
import uuid
from typing import Iterable

from backend.models.schemas import (
    Conflict,
    ConflictType,
    Entity,
    Severity,
    SourceType,
)

log = logging.getLogger(__name__)


def _is_say_vs_do(a: Entity, b: Entity) -> bool:
    """SAY_VS_DO: one side is meeting/slack ("say") and other is github ("do")."""
    say = {SourceType.MEETING, SourceType.SLACK}
    do = {SourceType.GITHUB}
    pair = {a.source_type, b.source_type}
    return bool(pair & say) and bool(pair & do)


def _classify_type(relationship: str, a: Entity, b: Entity) -> ConflictType | None:
    if relationship == "same_concept":
        # Cross-team duplication has top priority: if team A plans to build
        # something team B already has (or is building), the actionable
        # signal is "don't duplicate work" — even if the source pair looks
        # like meeting-vs-github (which would otherwise be SAY_VS_DO).
        if a.team != b.team:
            return ConflictType.DUPLICATION
        # Same team, meeting/slack vs github: classic say-vs-do mismatch
        # (we said one thing in the room, the code does another).
        if _is_say_vs_do(a, b):
            return ConflictType.SAY_VS_DO
        return None  # same team, same source family — not notable
    if relationship == "conflicting":
        return ConflictType.CONTRADICTION
    if relationship == "dependent":
        return ConflictType.HIDDEN_DEPENDENCY
    return None


def _severity(
    conflict_type: ConflictType, confidence: float, similarity: float
) -> Severity:
    if conflict_type == ConflictType.CONTRADICTION:
        return Severity.CRITICAL
    if conflict_type == ConflictType.SAY_VS_DO and confidence > 0.7:
        return Severity.CRITICAL
    if conflict_type == ConflictType.DUPLICATION and confidence > 0.7:
        return Severity.CRITICAL
    if conflict_type == ConflictType.HIDDEN_DEPENDENCY:
        return Severity.WARNING
    if confidence > 0.6 or similarity > 0.7:
        return Severity.WARNING
    return Severity.INFO


def _recommendation(conflict_type: ConflictType, a: Entity, b: Entity) -> str:
    """One-sentence action. Kept terse — the dashboard renders it as a single
    row, not a paragraph."""
    team_a, team_b = a.team, b.team

    if conflict_type == ConflictType.DUPLICATION:
        # Surface the side that's already in code (vs the side that's planning),
        # so the recommendation reads like "B already has this; A reuse it".
        coded = next(
            (e for e in (a, b) if e.source_type == SourceType.GITHUB), None
        )
        if coded is not None:
            other = b if coded is a else a
            return (
                f"{coded.team} already has this in code — {other.team} should "
                f"reuse before building."
            )
        return f"Pick a single owner between {team_a} and {team_b} before more code lands."

    if conflict_type == ConflictType.CONTRADICTION:
        return f"{team_a} and {team_b} disagree — escalate and reconcile before either ships."

    if conflict_type == ConflictType.HIDDEN_DEPENDENCY:
        return f"{team_b} depends on {team_a}'s decision — confirm timelines align."

    if conflict_type == ConflictType.SAY_VS_DO:
        spoken = a if a.source_type in {SourceType.MEETING, SourceType.SLACK} else b
        coded = b if spoken is a else a
        return (
            f"Code in {coded.team} diverges from what {spoken.team} said — "
            f"reconcile or revert."
        )

    return "Review with both teams."


def classify_conflicts(normalized: Iterable[dict]) -> list[Conflict]:
    """Turn normalized pair dicts into typed Conflict objects."""
    conflicts: list[Conflict] = []
    for item in normalized:
        a: Entity = item["entity_a"]
        b: Entity = item["entity_b"]
        relationship = item.get("relationship", "unrelated")
        confidence = float(item.get("confidence", 0.0))
        similarity = float(item.get("similarity", 0.0))

        conflict_type = _classify_type(relationship, a, b)
        if conflict_type is None:
            continue
        if confidence < 0.4 and similarity < 0.55:
            # Low-quality signal — drop instead of polluting the dashboard.
            continue

        severity = _severity(conflict_type, confidence, similarity)
        conflict = Conflict(
            id=f"conf-{uuid.uuid4().hex[:10]}",
            conflict_type=conflict_type,
            severity=severity,
            entity_a=a,
            entity_b=b,
            similarity_score=similarity,
            explanation=item.get("explanation", "")
            or "Cross-team semantic match detected.",
            recommendation=_recommendation(conflict_type, a, b),
        )
        conflicts.append(conflict)

    # Sort by severity then similarity for nicer dashboard display.
    sev_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
    conflicts.sort(key=lambda c: (sev_order[c.severity], -c.similarity_score))
    return conflicts
