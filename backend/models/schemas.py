from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    MEETING = "meeting"
    GITHUB = "github"
    SLACK = "slack"
    TICKET = "ticket"


class DecisionType(str, Enum):
    DECISION = "decision"
    PLAN = "plan"
    COMMITMENT = "commitment"
    CONCERN = "concern"
    DEPENDENCY = "dependency"


class ConflictType(str, Enum):
    DUPLICATION = "duplication"
    CONTRADICTION = "contradiction"
    HIDDEN_DEPENDENCY = "dependency"
    SAY_VS_DO = "say_vs_do"


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Entity(BaseModel):
    id: str
    name: str
    description: str
    source_type: SourceType
    source_id: str
    team: str
    decision_type: DecisionType
    timestamp: datetime
    speaker: Optional[str] = None
    confidence: float = 1.0
    raw_text: str = ""


class EntityEmbedding(BaseModel):
    entity: Entity
    embedding: list[float]


class Conflict(BaseModel):
    id: str
    conflict_type: ConflictType
    severity: Severity
    entity_a: Entity
    entity_b: Entity
    similarity_score: float
    explanation: str
    recommendation: str


class TeamSummary(BaseModel):
    team: str
    active_projects: list[str] = Field(default_factory=list)
    recent_decisions: list[Entity] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class SyncLayerReport(BaseModel):
    entities: list[Entity]
    conflicts: list[Conflict]
    team_summaries: list[TeamSummary]
    generated_at: datetime


class IngestEvent(BaseModel):
    """Live event used by the dashboard's event feed."""

    id: str
    source_type: SourceType
    team: str
    description: str
    entities_extracted: int
    timestamp: datetime
