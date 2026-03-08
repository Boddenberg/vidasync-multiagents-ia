from vidasync_multiagents_ia.state import OrchestratorState


def executor_agent(state: OrchestratorState) -> OrchestratorState:
    route = state.get("route", "planning")
    plan = state.get("plan", "No plan generated")
    context = state.get("context_chunks", [])
    answer = (
        f"Route selected: {route}\n"
        f"Plan:\n{plan}\n"
        f"Context chunks: {len(context)}"
    )
    return {"output": answer}
