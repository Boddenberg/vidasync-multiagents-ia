from vidasync_multiagents_ia.state import OrchestratorState


def planner_agent(state: OrchestratorState) -> OrchestratorState:
    context = "\n".join(state.get("context_chunks", []))
    plan = (
        "1. Clarify objective\n"
        "2. Select tools and constraints\n"
        "3. Execute in controlled steps\n"
        f"\nContext:\n{context}"
    )
    return {"plan": plan}
