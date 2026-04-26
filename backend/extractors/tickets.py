"""Project-ticket extractor (Jira/Linear style JSON)."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from backend.config import CLAUDE_EXTRACTION_MODEL
from backend.extractors._claude import call_claude_json
from backend.models.schemas import DecisionType, Entity, SourceType

log = logging.getLogger(__name__)


EXTRACTION_PROMPT = """You are analyzing project tickets for team "{team}".

Tickets:
{tickets}

For each ticket extract:
- name: Short identifier including the ticket id (e.g., "BACK-201: JWT auth service")
- description: 1-2 sentence summary
- decision_type: One of [decision, plan, commitment, concern, dependency]
- speaker: The assignee (or "unassigned")
- confidence: 0.0 to 1.0 based on how concrete the ticket is
- raw_text: Title + description joined

Treat in-progress / done tickets as commitments. Treat backlog tickets as plans.
If a ticket explicitly mentions another team or service it depends on, mark it dependency.

Return ONLY valid JSON array."""


def load_tickets_from_json(json_path: str) -> list[dict]:
    with open(json_path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of tickets in {json_path}")
    return data


def format_tickets(tickets: list[dict]) -> str:
    lines = []
    for t in tickets:
        labels = ", ".join(t.get("labels", [])) or "—"
        lines.append(
            f"[{t.get('id','?')}] {t.get('title','')}\n"
            f"  status={t.get('status','?')} priority={t.get('priority','?')} "
            f"assignee={t.get('assignee','?')}\n"
            f"  labels: {labels}\n"
            f"  description: {t.get('description','')}"
        )
    return "\n\n".join(lines)


def extract_entities_from_tickets(
    tickets: list[dict], team: str, source_id: str
) -> list[Entity]:
    if not tickets:
        return []
    prompt = EXTRACTION_PROMPT.format(team=team, tickets=format_tickets(tickets))
    raw = call_claude_json(prompt, max_tokens=3000, model=CLAUDE_EXTRACTION_MODEL)
    if not isinstance(raw, list):
        log.warning("Tickets extractor expected list, got %r", type(raw))
        return []

    now = datetime.utcnow()
    entities: list[Entity] = []
    for item in raw:
        try:
            decision_type = DecisionType(item.get("decision_type", "plan"))
        except ValueError:
            decision_type = DecisionType.PLAN
        entities.append(
            Entity(
                id=f"tkt-{source_id}-{uuid.uuid4().hex[:8]}",
                name=str(item.get("name", "")).strip()[:200],
                description=str(item.get("description", "")).strip(),
                source_type=SourceType.TICKET,
                source_id=source_id,
                team=team,
                decision_type=decision_type,
                timestamp=now,
                speaker=item.get("speaker"),
                confidence=float(item.get("confidence", 0.85)),
                raw_text=str(item.get("raw_text", "")),
            )
        )
    return entities


def process_tickets(json_path: str, team: str) -> list[Entity]:
    tickets = load_tickets_from_json(json_path)
    source_id = json_path.rsplit("/", 1)[-1].replace(".json", "")
    return extract_entities_from_tickets(tickets, team, source_id)
