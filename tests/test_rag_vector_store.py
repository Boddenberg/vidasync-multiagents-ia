from langchain_core.documents import Document

from vidasync_multiagents_ia.rag import vector_store


class _FakeRagService:
    def ingest(self, *, force_rebuild: bool = False):
        class _Summary:
            total_sources = 3
            total_chunks = 8
            embedder_name = "hash_embedding_v1"
            vector_dimensions = 128

        assert force_rebuild is True
        return _Summary()

    def retrieve(self, *, query: str):
        assert query == "fibra"
        return [Document(page_content="contexto", metadata={"source_path": "knowledge/faq.md"})]

    def build_context(self, *, query: str):
        assert query == "hidratar"
        docs = [Document(page_content="contexto 2", metadata={"source_path": "knowledge/dicas.md"})]
        return "[doc_1] contexto 2", docs


def test_vector_store_fachada_reusa_servico(monkeypatch) -> None:
    fake = _FakeRagService()
    monkeypatch.setattr(vector_store, "_get_rag_service", lambda: fake)

    summary = vector_store.reindex_nutrition_knowledge(force_rebuild=True)
    docs = vector_store.retrieve_context("fibra")
    context, context_docs = vector_store.build_context_for_query("hidratar")

    assert summary["total_sources"] == 3
    assert summary["total_chunks"] == 8
    assert summary["embedder_name"] == "hash_embedding_v1"
    assert len(docs) == 1
    assert context.startswith("[doc_1]")
    assert len(context_docs) == 1

