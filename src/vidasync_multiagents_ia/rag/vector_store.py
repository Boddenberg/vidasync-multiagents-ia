from langchain_core.documents import Document


def retrieve_context(query: str) -> list[Document]:
    # Placeholder RAG strategy until embeddings/index are connected.
    return [
        Document(page_content=f"Knowledge base placeholder for query: {query}", metadata={"source": "stub"})
    ]
