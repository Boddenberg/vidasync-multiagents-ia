from typing import Callable

from langchain_core.documents import Document

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.rag.vector_store import build_context_for_query, retrieve_context
from vidasync_multiagents_ia.services.calorias_texto_service import CaloriasTextoService
from vidasync_multiagents_ia.services.chat_tools.executor import ChatToolExecutor
from vidasync_multiagents_ia.services.chat_tools.nutricao_tools import (
    BuscarReceitasTool,
    CadastrarPratoTool,
    CalcularCaloriasTool,
    CalcularImcTool,
    CalcularMacrosTool,
    ConsultarConhecimentoNutricionalTool,
    SugerirSubstituicoesTool,
)


def build_chat_tool_executor(
    *,
    settings: Settings,
    client: OpenAIClient,
    calorias_service: CaloriasTextoService,
    rag_context_builder: Callable[[str], tuple[str, list[Document]]] | None = None,
    rag_retriever: Callable[[str], list[Document]] | None = None,
) -> ChatToolExecutor:
    retriever = rag_retriever or retrieve_context
    if rag_context_builder is not None:
        context_builder = rag_context_builder
    elif rag_retriever is not None:
        context_builder = _build_context_from_retriever(retriever)
    else:
        context_builder = build_context_for_query
    tools = [
        CalcularCaloriasTool(calorias_service=calorias_service),
        CalcularMacrosTool(calorias_service=calorias_service),
        CalcularImcTool(),
        BuscarReceitasTool(
            settings=settings,
            client=client,
            rag_context_builder=context_builder,
            rag_retriever=retriever,
        ),
        SugerirSubstituicoesTool(
            settings=settings,
            client=client,
            rag_context_builder=context_builder,
            rag_retriever=retriever,
        ),
        CadastrarPratoTool(),
        ConsultarConhecimentoNutricionalTool(
            settings=settings,
            client=client,
            rag_context_builder=context_builder,
            rag_retriever=retriever,
        ),
    ]
    return ChatToolExecutor(tools=tools)


def _build_context_from_retriever(
    retriever: Callable[[str], list[Document]],
) -> Callable[[str], tuple[str, list[Document]]]:
    def _inner(query: str) -> tuple[str, list[Document]]:
        docs = retriever(query)
        context_lines = []
        for index, doc in enumerate(docs[:4], start=1):
            source = str(doc.metadata.get("source_path") or doc.metadata.get("source") or "desconhecido")
            context_lines.append(f"[doc_{index} source={source}] {doc.page_content}")
        context = "\n".join(context_lines).strip()
        return context, docs

    return _inner
