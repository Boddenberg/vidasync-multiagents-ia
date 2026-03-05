from typing import Any, TypedDict


class OrchestratorState(TypedDict, total=False):
    query: str
    route: str
    context_chunks: list[str]
    plan: str
    output: str
    metadata: dict[str, Any]
