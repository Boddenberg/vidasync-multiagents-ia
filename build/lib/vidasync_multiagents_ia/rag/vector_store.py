from functools import lru_cache

from langchain_core.documents import Document

from vidasync_multiagents_ia.config import get_settings
from vidasync_multiagents_ia.rag.service import NutritionRagService


@lru_cache(maxsize=1)
def _get_rag_service() -> NutritionRagService:
    settings = get_settings()
    return NutritionRagService(settings=settings)


def reindex_nutrition_knowledge(*, force_rebuild: bool = True) -> dict[str, str | int]:
    summary = _get_rag_service().ingest(force_rebuild=force_rebuild)
    return {
        "total_sources": summary.total_sources,
        "total_chunks": summary.total_chunks,
        "embedder_name": summary.embedder_name,
        "vector_dimensions": summary.vector_dimensions,
    }


def retrieve_context(query: str) -> list[Document]:
    return _get_rag_service().retrieve(query=query)


def build_context_for_query(query: str) -> tuple[str, list[Document]]:
    return _get_rag_service().build_context(query=query)
