import logging
from threading import Lock

from langchain_core.documents import Document

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.rag.chunking import SlidingWindowChunker
from vidasync_multiagents_ia.rag.context_builder import RagContextBuilder
from vidasync_multiagents_ia.rag.embeddings import TextEmbedder, build_text_embedder
from vidasync_multiagents_ia.rag.loaders import NutritionKnowledgeLoader
from vidasync_multiagents_ia.rag.models import RagIngestionSummary
from vidasync_multiagents_ia.rag.vector_index import InMemoryVectorIndex


class NutritionRagService:
    # /**** Orquestra ingestao e retrieval de RAG sem acoplar com endpoint ou LangGraph. ****/
    def __init__(
        self,
        *,
        settings: Settings,
        loader: NutritionKnowledgeLoader | None = None,
        chunker: SlidingWindowChunker | None = None,
        embedder: TextEmbedder | None = None,
        index: InMemoryVectorIndex | None = None,
        context_builder: RagContextBuilder | None = None,
    ) -> None:
        self._settings = settings
        self._loader = loader or NutritionKnowledgeLoader()
        self._chunker = chunker or SlidingWindowChunker(
            chunk_size=max(200, settings.rag_chunk_size),
            chunk_overlap=max(0, min(settings.rag_chunk_overlap, settings.rag_chunk_size - 1)),
        )
        self._embedder = embedder or build_text_embedder(settings)
        self._index = index or InMemoryVectorIndex()
        self._context_builder = context_builder or RagContextBuilder(max_chars=settings.rag_context_max_chars)
        self._lock = Lock()
        self._ingested = False
        self._last_summary = RagIngestionSummary(
            total_sources=0,
            total_chunks=0,
            embedder_name=self._embedder.name,
            vector_dimensions=0,
        )
        self._logger = logging.getLogger(__name__)

    @property
    def last_summary(self) -> RagIngestionSummary:
        return self._last_summary

    def ingest(self, *, force_rebuild: bool = False) -> RagIngestionSummary:
        with self._lock:
            if self._ingested and not force_rebuild:
                return self._last_summary

            sources = self._loader.load_sources(docs_dir=self._settings.vidasync_docs_dir)
            chunks = self._chunker.chunk_sources(sources=sources)
            embeddings = self._embedder.embed_texts(texts=[chunk.text for chunk in chunks]) if chunks else []
            self._index.rebuild(chunks=chunks, embeddings=embeddings)
            self._ingested = True
            self._last_summary = RagIngestionSummary(
                total_sources=len(sources),
                total_chunks=len(chunks),
                embedder_name=self._embedder.name,
                vector_dimensions=self._index.dimensions,
            )
            self._logger.info(
                "rag.ingest.completed",
                extra={
                    "docs_dir": self._settings.vidasync_docs_dir,
                    "total_sources": len(sources),
                    "total_chunks": len(chunks),
                    "embedder": self._embedder.name,
                    "vector_dimensions": self._index.dimensions,
                    "force_rebuild": force_rebuild,
                },
            )
            return self._last_summary

    def retrieve(self, *, query: str, top_k: int | None = None) -> list[Document]:
        if not query.strip():
            return []
        self.ingest()
        try:
            query_embedding = self._embedder.embed_query(query=query)
            hits = self._index.search(
                query_embedding=query_embedding,
                top_k=max(1, top_k or self._settings.rag_top_k),
                min_score=self._settings.rag_min_score,
            )
            _, docs = self._context_builder.build(hits=hits)
            self._logger.info(
                "rag.retrieve.completed",
                extra={
                    "query_chars": len(query),
                    "top_k": top_k or self._settings.rag_top_k,
                    "hits": len(hits),
                    "docs_returned": len(docs),
                },
            )
            return docs
        except Exception:  # noqa: BLE001
            self._logger.exception("rag.retrieve.failed", extra={"query_chars": len(query)})
            return []

    def build_context(self, *, query: str, top_k: int | None = None) -> tuple[str, list[Document]]:
        if not query.strip():
            return "", []
        self.ingest()
        try:
            query_embedding = self._embedder.embed_query(query=query)
            hits = self._index.search(
                query_embedding=query_embedding,
                top_k=max(1, top_k or self._settings.rag_top_k),
                min_score=self._settings.rag_min_score,
            )
            context, docs = self._context_builder.build(hits=hits)
            self._logger.info(
                "rag.context.completed",
                extra={
                    "query_chars": len(query),
                    "top_k": top_k or self._settings.rag_top_k,
                    "hits": len(hits),
                    "context_chars": len(context),
                },
            )
            return context, docs
        except Exception:  # noqa: BLE001
            self._logger.exception("rag.context.failed", extra={"query_chars": len(query)})
            return "", []
