import logging

from vidasync_multiagents_ia.graph import build_graph


class OrchestratorService:
    def __init__(self) -> None:
        self._compiled_graph = build_graph()
        self._logger = logging.getLogger(__name__)

    def orchestrate(self, query: str) -> str:
        self._logger.info("orchestrator.started", extra={"query_chars": len(query)})
        state = self._compiled_graph.invoke({"query": query})
        output = state.get("output", "")
        self._logger.info("orchestrator.completed", extra={"output_chars": len(output)})
        return output
