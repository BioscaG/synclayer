"""Slack channel extractor.

Either pulls live messages from the Slack Web API (via slack-sdk) or reads a
JSON snapshot for the demo.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from backend.config import CLAUDE_EXTRACTION_MODEL, SLACK_BOT_TOKEN
from backend.extractors._claude import call_claude_json
from backend.models.schemas import DecisionType, Entity, SourceType

log = logging.getLogger(__name__)


EXTRACTION_PROMPT = """You are analyzing Slack messages from channel "#{channel}" for team "{team}".

Messages:
{messages}

Slack conversations are informal. Extract entities even from casual language:
- "gonna use X" = plan
- "let's just do X" = decision
- "I'll take care of X" = commitment
- "worried about X" = concern
- "we need X from Y team" = dependency

Be aggressive about extraction — important decisions are often buried in casual conversation.
Aim for 3-8 entities.

Each entity needs:
- name: Short specific identifier
- description: 1-2 sentence summary
- decision_type: One of [decision, plan, commitment, concern, dependency]
- speaker: Slack user / display name
- confidence: 0.0 to 1.0
- raw_text: Quoted message excerpt

Return ONLY valid JSON array."""


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------
def fetch_slack_messages(
    channel_id: str, limit: int = 100, *, token: Optional[str] = None
) -> list[dict]:
    """Fetch the latest messages from a Slack channel using slack-sdk.

    ``token`` overrides the global ``SLACK_BOT_TOKEN`` env var — used by the
    workspace-level OAuth flow so each SyncLayer workspace can talk to its
    own Slack workspace.
    """
    auth_token = token or SLACK_BOT_TOKEN
    if not auth_token:
        raise RuntimeError(
            "No Slack bot token available — connect Slack from Settings or set "
            "SLACK_BOT_TOKEN"
        )
    from slack_sdk import WebClient

    client = WebClient(token=auth_token)
    result = client.conversations_history(channel=channel_id, limit=limit)
    raw_messages = result.get("messages", []) or []

    # Resolve user display names lazily.
    user_cache: dict[str, str] = {}

    def resolve_user(uid: Optional[str]) -> str:
        if not uid:
            return "unknown"
        if uid in user_cache:
            return user_cache[uid]
        try:
            info = client.users_info(user=uid)
            name = (
                info.get("user", {}).get("real_name")
                or info.get("user", {}).get("name")
                or uid
            )
        except Exception:  # noqa: BLE001
            name = uid
        user_cache[uid] = name
        return name

    messages = []
    for m in reversed(raw_messages):  # chronological order
        if m.get("subtype"):  # skip channel join etc.
            continue
        ts = m.get("ts", "0")
        try:
            timestamp = datetime.fromtimestamp(float(ts)).isoformat()
        except (TypeError, ValueError):
            timestamp = ts
        messages.append(
            {
                "user": resolve_user(m.get("user")),
                "text": m.get("text", ""),
                "timestamp": timestamp,
                "thread_replies": [],
            }
        )

        # Pull thread replies if present.
        if m.get("thread_ts") and m.get("reply_count"):
            try:
                replies = client.conversations_replies(
                    channel=channel_id, ts=m["thread_ts"]
                ).get("messages", [])
                for r in replies[1:]:
                    messages[-1]["thread_replies"].append(
                        {
                            "user": resolve_user(r.get("user")),
                            "text": r.get("text", ""),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                log.debug("Could not fetch thread replies: %s", exc)

    return messages


def fetch_slack_messages_from_json(json_path: str) -> tuple[list[dict], str]:
    """Read a Slack snapshot. Returns (messages, channel_name)."""
    with open(json_path) as f:
        data = json.load(f)

    if isinstance(data, list):
        return data, json_path.rsplit("/", 1)[-1].replace(".json", "")
    return data.get("messages", []), data.get("channel", "unknown")


def format_slack_messages(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        lines.append(f"{m.get('user','?')}: {m.get('text','')}")
        for r in m.get("thread_replies", []) or []:
            lines.append(f"   ↳ {r.get('user','?')}: {r.get('text','')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def extract_entities_from_slack(
    messages: list[dict], team: str, channel_name: str
) -> list[Entity]:
    if not messages:
        return []
    prompt = EXTRACTION_PROMPT.format(
        team=team, channel=channel_name, messages=format_slack_messages(messages)
    )
    raw = call_claude_json(prompt, max_tokens=2500, model=CLAUDE_EXTRACTION_MODEL)
    if not isinstance(raw, list):
        log.warning("Slack extractor expected list, got %r", type(raw))
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
                id=f"slk-{uuid.uuid4().hex[:10]}",
                name=str(item.get("name", "")).strip()[:200],
                description=str(item.get("description", "")).strip(),
                source_type=SourceType.SLACK,
                source_id=channel_name,
                team=team,
                decision_type=decision_type,
                timestamp=now,
                speaker=item.get("speaker"),
                confidence=float(item.get("confidence", 0.7)),
                raw_text=str(item.get("raw_text", "")),
            )
        )
    return entities


def process_slack(
    *,
    channel_id: Optional[str] = None,
    json_path: Optional[str] = None,
    team: str,
    token: Optional[str] = None,
) -> list[Entity]:
    """Main entry point — choose live API or pre-fetched JSON."""
    if not channel_id and not json_path:
        raise ValueError("Either channel_id or json_path must be provided")

    if json_path:
        messages, channel_name = fetch_slack_messages_from_json(json_path)
    else:
        messages = fetch_slack_messages(channel_id, token=token)  # type: ignore[arg-type]
        channel_name = channel_id  # type: ignore[assignment]

    return extract_entities_from_slack(messages, team, channel_name)
