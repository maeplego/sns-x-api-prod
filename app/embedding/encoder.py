"""Deterministic text embeddings for the tutorial (no ML model dependency)."""

import hashlib
import math

from app.core.embedding_models import EMBEDDING_DIM


def _l2_normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0:
        return values
    return [v / norm for v in values]


def embed_text(text: str) -> list[float]:
    """Map post body to a unit vector in R^384."""
    normalized = text.strip().lower()
    values: list[float] = []
    for i in range(EMBEDDING_DIM):
        digest = hashlib.sha256(f"{normalized}:{i}".encode()).digest()
        val = (int.from_bytes(digest[:4], "big") / 2**32) * 2 - 1
        values.append(val)
    return _l2_normalize(values)


def mean_embedding(embeddings: list[list[float]]) -> list[float] | None:
    if not embeddings:
        return None
    dim = len(embeddings[0])
    sums = [0.0] * dim
    for vector in embeddings:
        for i, value in enumerate(vector):
            sums[i] += value
    return _l2_normalize([v / len(embeddings) for v in sums])


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
