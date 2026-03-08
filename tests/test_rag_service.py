from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.rag.service import NutritionRagService


def test_rag_service_ingest_retrieve_and_build_context(tmp_path) -> None:
    (tmp_path / "faq.md").write_text(
        "Fibra alimentar ajuda saciedade e saude intestinal.",
        encoding="utf-8",
    )
    (tmp_path / "hidrata.txt").write_text(
        "Hidratacao regular durante o dia melhora adesao ao plano.",
        encoding="utf-8",
    )
    settings = Settings(
        vidasync_docs_dir=str(tmp_path),
        rag_embedding_provider="hash",
        rag_chunk_size=80,
        rag_chunk_overlap=10,
        rag_top_k=3,
        rag_min_score=0.0,
        rag_context_max_chars=500,
    )
    service = NutritionRagService(settings=settings)

    summary = service.ingest(force_rebuild=True)
    docs = service.retrieve(query="fibra intestinal")
    context, docs_for_context = service.build_context(query="hidratacao diaria")

    assert summary.total_sources == 2
    assert summary.total_chunks >= 2
    assert summary.vector_dimensions > 0
    assert docs
    assert docs_for_context
    assert context
    assert len(context) <= 500
    assert any("source_path" in doc.metadata for doc in docs_for_context)

