from vidasync_multiagents_ia.rag.vector_store import retrieve_context
from vidasync_multiagents_ia.state import OrchestratorState


def retrieve_agent(state: OrchestratorState) -> OrchestratorState:
    query = state.get("query", "")
    docs = retrieve_context(query)
    return {"context_chunks": [doc.page_content for doc in docs]}
