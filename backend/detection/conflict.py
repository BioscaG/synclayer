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
        # Same concept across SAY (meeting/slack) vs DO (code) is the most
        # interesting signal even if same team — it's a SAY_VS_DO mismatch.
        if _is_say_vs_do(a, b):
            return ConflictType.SAY_VS_DO
        if a.team != b.team:
            return ConflictType.DUPLICATION
        return None  # same concept, same team, both said: nothing notable
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
    team_a, team_b = a.team, b.team
    if conflict_type == ConflictType.DUPLICATION:
        return (
            f"⚠️ {team_a} and {team_b} are both working on '{a.name}' / '{b.name}'. "
            f"Hold a 30-minute alignment meeting before more code is written, "
            f"and assign a single owner."
        )
    if conflict_type == ConflictType.CONTRADICTION:
        return (
            f"❗ {team_a} and {team_b} have made conflicting decisions about "
            f"'{a.name}' vs '{b.name}'. Escalate to leadership immediately and "
            f"reconcile before either side ships."
        )
    if conflict_type == ConflictType.HIDDEN_DEPENDENCY:
        return (
            f"🔗 {team_b} depends on {team_a}'s decision around '{a.name}'. "
            f"Notify {team_b} this week and confirm timelines align."
        )
    if conflict_type == ConflictType.SAY_VS_DO:
        spoken = a if a.source_type in {SourceType.MEETING, SourceType.SLACK} else b
        coded = b if spoken is a else a
        return (
            f"🚨 Code in {coded.team} ('{coded.name}') diverges from what was said "
            f"in {spoken.source_type.value} ('{spoken.name}'). Confirm whether the "
            f"verbal decision was reversed — if not, revert or update the spec."
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
