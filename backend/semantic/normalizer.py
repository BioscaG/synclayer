"""Cross-source semantic normalization.

FAISS/cosine tells us two entities look similar. Claude tells us *why* — same
concept, contradiction, dependency, or false positive.

The normalizer supports a pair cache so we don't re-pay Claude for pairs that
were already judged in a previous run.
"""
from __future__ import annotations

import logging
from typing import Callable, Iterable, Optional

from backend.config import CLAUDE_NORMALIZER_MODEL, NORMALIZER_BATCH_SIZE
from backend.extractors._claude import call_claude_json
from backend.models.schemas import Entity

log = logging.getLogger(__name__)


PROMPT = """Given pairs of entities from DIFFERENT sources (meetings, code repos, Slack, tickets),
determine if they refer to the same underlying concept or relate in some other way.

For each pair, analyze:
1. Same technical concept? ("login system" ≈ "authentication module")
2. Same project/feature? ("AUTH-247" ≈ "JWT implementation")
3. Conflicting approaches? ("REST API" vs "GraphQL migration")
4. Dependency between them? (one team's plan blocks/needs another's work)

IMPORTANT: Different teams use different words for the same thing.
"auth service", "login module", and "sign-in flow" can all be the same concept.
The most valuable conflicts are between what's SAID (meetings/Slack) and what's DONE (code).

Pairs to evaluate:
{pairs}

Return ONLY a valid JSON array. One entry per input pair, in order:
{{
  "pair_index": <int — same as the input>,
  "relationship": "same_concept" | "conflicting" | "dependent" | "unrelated",
  "confidence": <0.0 to 1.0>,
  "explanation": "<1-2 sentences>"
}}"""


def _format_pair(idx: int, a: Entity, b: Entity) -> str:
    return (
        f"Pair {idx}:\n"
        f"  A) [{a.source_type.value} | team={a.team} | type={a.decision_type.value}] "
        f"{a.name}\n"
        f"     description: {a.description}\n"
        f"     raw: {a.raw_text[:200]}\n"
        f"  B) [{b.source_type.value} | team={b.team} | type={b.decision_type.value}] "
        f"{b.name}\n"
        f"     description: {b.description}\n"
        f"     raw: {b.raw_text[:200]}"
    )


def _batched(iterable: list, size: int) -> Iterable[list]:
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


# Type aliases for pluggable cache callbacks.
CacheGet = Callable[[str, str], Optional[dict]]
CachePut = Callable[[str, str], None]


def normalize_pairs(
    pairs: list[tuple[Entity, Entity, float]],
    *,
    cache_get: Optional[CacheGet] = None,
    cache_put: Optional[Callable[[str, str, dict], None]] = None,
) -> list[dict]:
    """Annotate each FAISS pair with a relationship + explanation.

    If cache_get / cache_put are provided, pairs already judged are taken from
    the cache instead of calling Claude. Newly judged pairs are written back.
    """
    if not pairs:
        return []

    # Split: cached vs to-call
    cached_results: dict[int, dict] = {}
    to_call: list[tuple[int, Entity, Entity, float]] = []

    for i, (a, b, score) in enumerate(pairs):
        cached = cache_get(a.id, b.id) if cache_get else None
        if cached:
            cached_results[i] = {
                "entity_a": a,
                "entity_b": b,
                "similarity": score,
                "relationship": cached.get("relationship", "unrelated"),
                "confidence": float(cached.get("confidence", 0.0)),
                "explanation": cached.get("explanation", ""),
                "pair_index": i,
                "from_cache": True,
            }
        else:
            to_call.append((i, a, b, score))

    if cached_results:
        log.info(
            "Normalizer cache hit on %d / %d pairs", len(cached_results), len(pairs)
        )

    annotated_by_index: dict[int, dict] = dict(cached_results)

    # Call Claude in batches for the new ones.
    for batch in _batched(to_call, NORMALIZER_BATCH_SIZE):
        formatted = "\n\n".join(
            _format_pair(local_i, a, b)
            for local_i, (_global_i, a, b, _s) in enumerate(batch)
        )
        prompt = PROMPT.format(pairs=formatted)
        try:
            raw = call_claude_json(
                prompt, max_tokens=2500, model=CLAUDE_NORMALIZER_MODEL
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Normalizer batch failed: %s", exc)
            raw = []

        if not isinstance(raw, list):
            log.warning("Normalizer expected list, got %r", type(raw))
            raw = []

        # Index responses by the local pair_index they should match.
        by_local: dict[int, dict] = {}
        for item in raw:
            try:
                by_local[int(item.get("pair_index"))] = item
            except (TypeError, ValueError):
                continue

        for local_i, (global_i, a, b, score) in enumerate(batch):
            r = by_local.get(local_i, {})
            relationship = r.get("relationship", "unrelated")
            confidence = float(r.get("confidence", 0.0))
            explanation = str(
                r.get("explanation", "Could not determine relationship.")
            )
            annotated_by_index[global_i] = {
                "entity_a": a,
                "entity_b": b,
                "similarity": score,
                "relationship": relationship,
                "confidence": confidence,
                "explanation": explanation,
                "pair_index": global_i,
                "from_cache": False,
            }
            if cache_put:
                cache_put(
                    a.id,
                    b.id,
                    {
                        "relationship": relationship,
                        "confidence": confidence,
                        "explanation": explanation,
                    },
                )

    return [annotated_by_index[i] for i in sorted(annotated_by_index)]
