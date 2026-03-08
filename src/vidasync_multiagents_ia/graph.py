from langgraph.graph import END, StateGraph

from vidasync_multiagents_ia.agents.executor import executor_agent
from vidasync_multiagents_ia.agents.planner import planner_agent
from vidasync_multiagents_ia.agents.retriever import retrieve_agent
from vidasync_multiagents_ia.agents.router import route_agent
from vidasync_multiagents_ia.state import OrchestratorState


def build_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("router", route_agent)
    graph.add_node("retrieve", retrieve_agent)
    graph.add_node("planner", planner_agent)
    graph.add_node("executor", executor_agent)

    graph.set_entry_point("router")
    graph.add_edge("router", "retrieve")
    graph.add_edge("retrieve", "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", END)

    return graph.compile()
