import math

from vidasync_multiagents_ia.rag.models import RagChunk, RagSearchHit


class InMemoryVectorIndex:
    def __init__(self) -> None:
        self._rows: list[tuple[RagChunk, list[float]]] = []
        self._dimensions: int = 0

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def rebuild(self, *, chunks: list[RagChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks e embeddings devem ter o mesmo tamanho.")
        self._rows = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            self._rows.append((chunk, embedding))
        self._dimensions = len(embeddings[0]) if embeddings else 0

    def search(self, *, query_embedding: list[float], top_k: int, min_score: float) -> list[RagSearchHit]:
        if not self._rows or not query_embedding:
            return []
        hits: list[RagSearchHit] = []
        for chunk, vector in self._rows:
            score = _cosine_similarity(query_embedding, vector)
            if score < min_score:
                continue
            hits.append(RagSearchHit(chunk=chunk, score=round(score, 6)))
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:top_k]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm <= 1e-12 or right_norm <= 1e-12:
        return 0.0
    return dot / (left_norm * right_norm)
