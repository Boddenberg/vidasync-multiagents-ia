from fastapi import FastAPI
from pydantic import BaseModel

from vidasync_multiagents_ia.graph import build_graph

app = FastAPI(title="VidaSync Multiagents IA", version="0.1.0")
compiled_graph = build_graph()


class OrchestrateRequest(BaseModel):
    query: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/orchestrate")
def orchestrate(payload: OrchestrateRequest) -> dict[str, str]:
    state = compiled_graph.invoke({"query": payload.query})
    return {"result": state.get("output", "")}
