"""Embedding generation + cross-team similarity search.

We use a NumPy cosine-similarity matrix instead of FAISS. For the dataset
sizes involved here (hundreds of entities), the matmul is sub-millisecond and
avoids FAISS's ABI/wheel compatibility issues on newer Python versions.
The semantic-similarity threshold is still controlled by FAISS_THRESHOLD.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from backend.config import EMBEDDING_MODEL, FAISS_THRESHOLD
from backend.models.schemas import Entity, EntityEmbedding

log = logging.getLogger(__name__)

_model = None


def _get_model():
    """Lazy-load sentence-transformers model (first load is slow)."""
    global _model
    if _model is None:
        log.info("Loading sentence-transformers model %s ...", EMBEDDING_MODEL)
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def create_entity_text(entity: Entity) -> str:
    """Build the text fed to the embedding model for an entity.

    Combining name + description + team + decision_type + raw_text gives the
    embedding richer signal than name alone.
    """
    parts = [
        entity.name,
        entity.description,
        f"team: {entity.team}",
        f"type: {entity.decision_type.value}",
    ]
    if entity.raw_text:
        parts.append(entity.raw_text[:200])
    return " | ".join(parts)


def embed_entities(entities: list[Entity]) -> list[EntityEmbedding]:
    """Generate embeddings for a list of entities."""
    if not entities:
        return []
    model = _get_model()
    texts = [create_entity_text(e) for e in entities]
    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return [
        EntityEmbedding(entity=e, embedding=v.tolist())
        for e, v in zip(entities, vectors)
    ]


class SemanticIndex:
    """Cosine-similarity index over entity embeddings (NumPy-backed).

    Vectors are L2-normalized so a single matmul gives the full pairwise
    cosine matrix. Equivalent to FAISS IndexFlatIP for this scale.
    """

    def __init__(self, embeddings: list[EntityEmbedding]):
        self.embeddings = embeddings
        self.entities = [e.entity for e in embeddings]
        self._matrix: Optional[np.ndarray] = None
        if embeddings:
            self._build()

    def _build(self) -> None:
        matrix = np.array([e.embedding for e in self.embeddings], dtype=np.float32)
        # Re-normalize defensively in case the caller didn't.
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = matrix / norms

    def _pairs(
        self,
        threshold: float,
        top_k: int,
        same_team: bool,
    ) -> list[tuple[Entity, Entity, float]]:
        if not self.embeddings or self._matrix is None:
            return []
        sims = self._matrix @ self._matrix.T
        np.fill_diagonal(sims, -1.0)
        n = sims.shape[0]
        k = min(top_k, n - 1) if n > 1 else 0
        if k == 0:
            return []

        top_idx = np.argpartition(-sims, kth=k - 1, axis=1)[:, :k]
        seen: set[tuple[str, str]] = set()
        results: list[tuple[Entity, Entity, float]] = []
        for i in range(n):
            ent_a = self.entities[i]
            for j in top_idx[i]:
                score = float(sims[i, j])
                if score < threshold:
                    continue
                ent_b = self.entities[int(j)]
                if same_team and ent_a.team != ent_b.team:
                    continue
                if not same_team and ent_a.team == ent_b.team:
                    continue
                pair = tuple(sorted((ent_a.id, ent_b.id)))
                if pair in seen:
                    continue
                seen.add(pair)
                results.append((ent_a, ent_b, score))
        results.sort(key=lambda t: t[2], reverse=True)
        return results

    def find_cross_team_matches(
        self,
        threshold: float = FAISS_THRESHOLD,
        top_k: int = 20,
    ) -> list[tuple[Entity, Entity, float]]:
        """De-duplicated (a, b, score) triples from DIFFERENT teams."""
        return self._pairs(threshold=threshold, top_k=top_k, same_team=False)

    def find_internal_duplications(
        self,
        threshold: float = 0.62,
        top_k: int = 10,
    ) -> list[tuple[Entity, Entity, float]]:
        """Same-team near-duplicate entities — internal redundancy / inefficiency.

        A higher default threshold than cross-team matching: within a team,
        the same words are common, so we want stronger semantic overlap
        before flagging.
        """
        return self._pairs(threshold=threshold, top_k=top_k, same_team=True)
