from vidasync_multiagents_ia.state import OrchestratorState


def route_agent(state: OrchestratorState) -> OrchestratorState:
    query = state.get("query", "").lower()
    route = "execution" if any(word in query for word in ["execute", "acao", "action"]) else "planning"
    return {"route": route, "metadata": {"router": "rule-based"}}
