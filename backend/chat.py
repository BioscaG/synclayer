"""Feature-aware chatbot helpers.

The chat endpoint is deliberately retrieval-first: it searches SyncLayer's
local memory, then asks the model to answer only from those matches. That keeps
the assistant grounded in the project instead of inventing functionality.
"""
from __future__ import annotations

import logging
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from backend.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from backend.extractors._claude import call_claude_json
from backend.models.schemas import Entity
from backend.semantic.embeddings import _get_model, create_entity_text
from backend.storage import Store

log = logging.getLogger(__name__)

ChatRole = Literal["user", "assistant"]
ChatStatus = Literal["found", "partial", "not_found", "empty", "model_unavailable"]


class ChatTurn(BaseModel):
    role: ChatRole
    content: str = Field(min_length=1, max_length=3000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=8)
    top_k: int = Field(default=8, ge=1, le=12)


class ChatMatch(BaseModel):
    entity: Entity
    score: float


class ChatResponse(BaseModel):
    answer: str
    matches: list[ChatMatch] = Field(default_factory=list)
    status: ChatStatus
    used_model: str


def _embed_query(text: str) -> np.ndarray:
    model = _get_model()
    vector = model.encode([text], convert_to_numpy=True, normalize_embeddings=True)[0]
    vector = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


def _search_matches(store: Store, query: str, top_k: int) -> list[ChatMatch]:
    entities, matrix = store.all_embeddings_matrix()
    if not entities or matrix.size == 0:
        return []

    query_vector = _embed_query(query)
    scores = matrix @ query_vector
    order = np.argsort(-scores)[:top_k]

    matches: list[ChatMatch] = []
    for idx in order:
        score = float(scores[int(idx)])
        # Keep a low threshold because user wording often differs from extracted
        # meeting/ticket/repo language, but do not send clearly unrelated noise.
        if score < 0.25:
            continue
        matches.append(ChatMatch(entity=entities[int(idx)], score=round(score, 4)))
    return matches


def _status_from_matches(matches: list[ChatMatch]) -> ChatStatus:
    if not matches:
        return "not_found"
    if matches[0].score >= 0.58:
        return "found"
    return "partial"


def _build_context(store: Store, matches: list[ChatMatch]) -> str:
    if not matches:
        return "No local functionality matches were found."

    matched_ids = {m.entity.id for m in matches}
    conflicts = [
        c
        for c in store.all_conflicts()
        if c.entity_a.id in matched_ids or c.entity_b.id in matched_ids
    ][:6]

    blocks: list[str] = []
    for i, match in enumerate(matches, start=1):
        entity = match.entity
        raw = (entity.raw_text or "").strip().replace("\n", " ")
        if len(raw) > 320:
            raw = f"{raw[:317]}..."
        blocks.append(
            "\n".join(
                [
                    f"[{i}] id: {entity.id}",
                    f"name: {entity.name}",
                    f"description: {entity.description}",
                    f"team: {entity.team}",
                    f"type: {entity.decision_type.value}",
                    f"source: {entity.source_type.value}:{entity.source_id}",
                    f"similarity: {match.score:.2f}",
                    f"raw_text: {raw}" if raw else "raw_text: n/a",
                ]
            )
        )

    if conflicts:
        blocks.append("Related conflicts:")
        for conflict in conflicts:
            blocks.append(
                "\n".join(
                    [
                        f"- {conflict.conflict_type.value} / {conflict.severity.value}",
                        f"  {conflict.entity_a.name} <-> {conflict.entity_b.name}",
                        f"  explanation: {conflict.explanation}",
                        f"  recommendation: {conflict.recommendation}",
                    ]
                )
            )

    return "\n\n".join(blocks)


def _build_history(history: list[ChatTurn]) -> str:
    if not history:
        return "No previous chat turns."
    recent = history[-6:]
    return "\n".join(f"{turn.role}: {turn.content}" for turn in recent)


def _fallback_answer(matches: list[ChatMatch], status: ChatStatus) -> str:
    if not matches:
        return (
            "No he encontrado una funcionalidad parecida en la memoria local. "
            "Prueba con otro nombre, equipo o una descripción más concreta."
        )

    first = matches[0]
    intro = (
        "He encontrado una funcionalidad muy parecida"
        if status == "found"
        else "He encontrado funcionalidades relacionadas, pero no una coincidencia perfecta"
    )
    return (
        f"{intro}: {first.entity.name} en {first.entity.team}. "
        f"Su descripción es: {first.entity.description}"
    )


def answer_chat(store: Store, req: ChatRequest) -> ChatResponse:
    matches = _search_matches(store, req.message, req.top_k)
    if not store.all_entities():
        return ChatResponse(
            answer=(
                "Todavía no hay funcionalidades en memoria. Ingeste reuniones, tickets, "
                "repos o Slack para que pueda comparar la pregunta con el proyecto."
            ),
            matches=[],
            status="empty",
            used_model="local",
        )

    status = _status_from_matches(matches)
    if not ANTHROPIC_API_KEY:
        return ChatResponse(
            answer=_fallback_answer(matches, status),
            matches=matches,
            status="model_unavailable",
            used_model="local",
        )

    system = (
        "You are SyncLayer's feature copilot. Answer in the same language as the "
        "user. Use only the local project evidence provided. If the evidence is "
        "weak or missing, say so clearly. Do not invent implementation status."
    )
    prompt = f"""
User question:
{req.message}

Recent chat:
{_build_history(req.history)}

Local project evidence:
{_build_context(store, matches)}

Return JSON with exactly:
{{
  "answer": "short useful answer grounded in the evidence",
  "status": "found|partial|not_found"
}}
""".strip()

    try:
        data = call_claude_json(
            prompt,
            system=system,
            max_tokens=900,
            temperature=0,
            model=CLAUDE_MODEL,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Chat model call failed: %s", exc)
        return ChatResponse(
            answer=_fallback_answer(matches, status),
            matches=matches,
            status="model_unavailable",
            used_model="local",
        )

    answer = str(data.get("answer") or "").strip()
    model_status = data.get("status")
    if model_status not in {"found", "partial", "not_found"}:
        model_status = status
    if not answer:
        answer = _fallback_answer(matches, model_status)

    return ChatResponse(
        answer=answer,
        matches=matches,
        status=model_status,
        used_model=CLAUDE_MODEL,
    )
