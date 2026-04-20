import hashlib
import math
import re
from typing import Protocol

from openai import OpenAI

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core.cache import TTLCache


class TextEmbedder(Protocol):
    name: str
    dimensions: int

    def embed_texts(self, *, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, *, query: str) -> list[float]:
        ...


class HashTextEmbedder:
    name = "hash_embedding_v1"

    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions

    def embed_texts(self, *, texts: list[str]) -> list[list[float]]:
        return [self._embed(value) for value in texts]

    def embed_query(self, *, query: str) -> list[float]:
        return self._embed(query)

    def _embed(self, value: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _tokenize(value)
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha1(token.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % self.dimensions
            sign = -1.0 if int(digest[8], 16) % 2 else 1.0
            vector[index] += sign
        return _normalize_vector(vector)


class OpenAITextEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.name = f"openai:{model}"
        self.dimensions = dimensions
        self._model = model
        self._client = OpenAI(api_key=api_key.strip(), timeout=timeout_seconds)

    def embed_texts(self, *, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._model, input=texts)
        vectors = [list(item.embedding) for item in response.data]
        return [_normalize_vector(vec) for vec in vectors]

    def embed_query(self, *, query: str) -> list[float]:
        response = self._client.embeddings.create(model=self._model, input=query)
        vector = list(response.data[0].embedding)
        return _normalize_vector(vector)


class CachingTextEmbedder:
    def __init__(self, *, inner: TextEmbedder, ttl_seconds: float, max_entries: int) -> None:
        self._inner = inner
        self.name = inner.name
        self.dimensions = inner.dimensions
        self._query_cache: TTLCache[str, list[float]] = TTLCache(
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
        )

    def embed_texts(self, *, texts: list[str]) -> list[list[float]]:
        return self._inner.embed_texts(texts=texts)

    def embed_query(self, *, query: str) -> list[float]:
        key = _query_cache_key(name=self.name, query=query)
        cached = self._query_cache.get(key)
        if cached is not None:
            return cached
        vector = self._inner.embed_query(query=query)
        self._query_cache.set(key, vector)
        return vector


def build_text_embedder(settings: Settings) -> TextEmbedder:
    inner = _build_inner_embedder(settings)
    ttl = getattr(settings, "rag_embedding_query_cache_ttl_seconds", 0.0)
    if ttl and ttl > 0.0:
        return CachingTextEmbedder(
            inner=inner,
            ttl_seconds=ttl,
            max_entries=getattr(settings, "rag_embedding_query_cache_max_entries", 256),
        )
    return inner


def _build_inner_embedder(settings: Settings) -> TextEmbedder:
    provider = settings.rag_embedding_provider.strip().lower()
    if provider in {"hash", "stub"}:
        return HashTextEmbedder()
    if provider == "openai":
        if settings.openai_api_key.strip():
            return OpenAITextEmbedder(
                api_key=settings.openai_api_key,
                model=settings.rag_embedding_model,
                timeout_seconds=settings.openai_timeout_seconds,
            )
        return HashTextEmbedder()

    # Modo auto: tenta OpenAI quando chave existe e cai para hash em ambiente local/offline.
    if settings.openai_api_key.strip():
        try:
            return OpenAITextEmbedder(
                api_key=settings.openai_api_key,
                model=settings.rag_embedding_model,
                timeout_seconds=settings.openai_timeout_seconds,
            )
        except Exception:  # noqa: BLE001
            return HashTextEmbedder()
    return HashTextEmbedder()


def _query_cache_key(*, name: str, query: str) -> str:
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()
    return f"{name}:{digest}"


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 1e-12:
        return vector
    return [value / norm for value in vector]


def _tokenize(text: str) -> list[str]:
    lowered = text.lower()
    return [token for token in re.split(r"[^a-zA-Z0-9]+", lowered) if token]
