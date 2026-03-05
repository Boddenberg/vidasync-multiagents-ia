# VidaSync Multiagents IA

Orquestrador de multiagents em Python para o ecossistema VidaSync.

## Stack
- LangGraph para orquestracao de fluxo de agentes
- LangChain para tools e modelos
- RAG com ChromaDB
- FastAPI para expor endpoint de orquestracao

## Como rodar
1. Crie o ambiente virtual:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
2. Instale dependencias:
   ```bash
   pip install -e .[dev]
   ```
3. Configure variaveis:
   ```bash
   copy .env.example .env
   # opcional: use .env.local para overrides locais
   ```
4. Suba a API:
   ```bash
   uvicorn vidasync_multiagents_ia.main:app --reload
   ```

## Endpoint inicial
- `POST /orchestrate`

Payload:
```json
{
  "query": "Quais sao os proximos passos para onboarding de cliente enterprise?"
}
```

## Estrutura
- `src/vidasync_multiagents_ia/graph.py`: define o StateGraph
- `src/vidasync_multiagents_ia/agents/`: agentes especializados
- `src/vidasync_multiagents_ia/rag/`: camada de retrieval
