from vidasync_multiagents_ia.rag.embeddings import CachingTextEmbedder


class _CountingEmbedder:
    name = "counting"
    dimensions = 4

    def __init__(self) -> None:
        self.query_calls = 0
        self.texts_calls = 0

    def embed_query(self, *, query: str) -> list[float]:
        self.query_calls += 1
        return [float(len(query)), 0.0, 0.0, 0.0]

    def embed_texts(self, *, texts: list[str]) -> list[list[float]]:
        self.texts_calls += 1
        return [[float(len(text)), 0.0, 0.0, 0.0] for text in texts]


def test_caching_embedder_reuses_query_vector() -> None:
    inner = _CountingEmbedder()
    cached = CachingTextEmbedder(inner=inner, ttl_seconds=60.0, max_entries=8)

    v1 = cached.embed_query(query="banana")
    v2 = cached.embed_query(query="banana")
    assert v1 == v2
    assert inner.query_calls == 1


def test_caching_embedder_distinct_queries_invoke_inner() -> None:
    inner = _CountingEmbedder()
    cached = CachingTextEmbedder(inner=inner, ttl_seconds=60.0, max_entries=8)

    cached.embed_query(query="abc")
    cached.embed_query(query="abcd")
    assert inner.query_calls == 2


def test_caching_embedder_passthrough_for_texts() -> None:
    inner = _CountingEmbedder()
    cached = CachingTextEmbedder(inner=inner, ttl_seconds=60.0, max_entries=8)

    cached.embed_texts(texts=["a", "b"])
    cached.embed_texts(texts=["a", "b"])
    assert inner.texts_calls == 2
