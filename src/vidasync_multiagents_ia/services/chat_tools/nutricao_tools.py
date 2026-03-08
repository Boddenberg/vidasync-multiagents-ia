import logging
import re
from typing import Callable

from langchain_core.documents import Document

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import record_chat_rag_usage
from vidasync_multiagents_ia.rag.vector_store import build_context_for_query
from vidasync_multiagents_ia.services.calorias_texto_service import CaloriasTextoService
from vidasync_multiagents_ia.services.chat_tools.contracts import (
    ChatToolExecutionInput,
    ChatToolExecutionOutput,
    ChatToolName,
)


class CalcularCaloriasTool:
    name: ChatToolName = "calcular_calorias"

    def __init__(self, *, calorias_service: CaloriasTextoService) -> None:
        self._calorias_service = calorias_service
        self._logger = logging.getLogger(__name__)

    def execute(self, *, data: ChatToolExecutionInput) -> ChatToolExecutionOutput:
        self._logger.info("chat_tool.calcular_calorias.started")
        response = self._calorias_service.calcular(
            texto=data.prompt,
            contexto="calcular_calorias_texto",
            idioma=data.idioma,
        )
        warnings = list(response.warnings)
        total = response.totais.calorias_kcal
        if total is None:
            warnings.append("Nao foi possivel calcular calorias totais.")
            resumo = "Nao consegui estimar as calorias totais com confianca."
            status = "parcial"
        else:
            resumo = f"Estimativa total: {round(total, 2)} kcal."
            status = "sucesso" if not warnings else "parcial"
        return ChatToolExecutionOutput(
            tool_name=self.name,
            status=status,
            resposta=resumo,
            warnings=warnings,
            precisa_revisao=bool(warnings),
            metadados={"calorias": response.model_dump(exclude_none=True)},
        )


class CalcularMacrosTool:
    name: ChatToolName = "calcular_macros"

    def __init__(self, *, calorias_service: CaloriasTextoService) -> None:
        self._calorias_service = calorias_service
        self._logger = logging.getLogger(__name__)

    def execute(self, *, data: ChatToolExecutionInput) -> ChatToolExecutionOutput:
        self._logger.info("chat_tool.calcular_macros.started")
        response = self._calorias_service.calcular(
            texto=data.prompt,
            contexto="calcular_calorias_texto",
            idioma=data.idioma,
        )
        totais = response.totais
        warnings = list(response.warnings)
        faltantes = []
        if totais.proteina_g is None:
            faltantes.append("proteina_g")
        if totais.carboidratos_g is None:
            faltantes.append("carboidratos_g")
        if totais.lipidios_g is None:
            faltantes.append("lipidios_g")
        if faltantes:
            warnings.append("Nao foi possivel fechar todos os macros.")

        resumo = (
            f"Macros totais estimados: proteina {round(totais.proteina_g or 0.0, 2)} g, "
            f"carboidratos {round(totais.carboidratos_g or 0.0, 2)} g, "
            f"lipidios {round(totais.lipidios_g or 0.0, 2)} g."
        )
        return ChatToolExecutionOutput(
            tool_name=self.name,
            status="parcial" if warnings else "sucesso",
            resposta=resumo,
            warnings=warnings,
            precisa_revisao=bool(warnings),
            metadados={
                "faltantes": faltantes,
                "macros": {
                    "proteina_g": totais.proteina_g,
                    "carboidratos_g": totais.carboidratos_g,
                    "lipidios_g": totais.lipidios_g,
                },
                "calorias": response.model_dump(exclude_none=True),
            },
        )


class CalcularImcTool:
    name: ChatToolName = "calcular_imc"

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def execute(self, *, data: ChatToolExecutionInput) -> ChatToolExecutionOutput:
        self._logger.info("chat_tool.calcular_imc.started")
        peso_kg = _extract_peso_kg(data.prompt)
        altura_m = _extract_altura_m(data.prompt)
        faltantes: list[str] = []
        if peso_kg is None:
            faltantes.append("peso_kg")
        if altura_m is None:
            faltantes.append("altura_m")

        if faltantes:
            return ChatToolExecutionOutput(
                tool_name=self.name,
                status="parcial",
                resposta="Para calcular IMC, informe peso e altura. Exemplo: 72 kg e 1,75 m.",
                warnings=["Dados insuficientes para calcular IMC."],
                precisa_revisao=True,
                metadados={"campos_faltantes": faltantes},
            )

        imc = round(peso_kg / (altura_m * altura_m), 2)
        classificacao = _classificar_imc(imc)
        return ChatToolExecutionOutput(
            tool_name=self.name,
            status="sucesso",
            resposta=f"Seu IMC estimado e {imc} ({classificacao}).",
            metadados={
                "imc": imc,
                "peso_kg": peso_kg,
                "altura_m": altura_m,
                "classificacao": classificacao,
            },
        )


class BuscarReceitasTool:
    name: ChatToolName = "buscar_receitas"

    def __init__(
        self,
        *,
        settings: Settings,
        client: OpenAIClient,
        rag_context_builder: Callable[[str], tuple[str, list[Document]]] | None = None,
        rag_retriever: Callable[[str], list[Document]] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        if rag_context_builder is not None:
            self._rag_context_builder = rag_context_builder
        elif rag_retriever is not None:
            self._rag_context_builder = _build_context_from_retriever(rag_retriever)
        else:
            self._rag_context_builder = build_context_for_query
        self._logger = logging.getLogger(__name__)

    def execute(self, *, data: ChatToolExecutionInput) -> ChatToolExecutionOutput:
        _ensure_openai_api_key(self._settings)
        self._logger.info("chat_tool.buscar_receitas.started")
        contexto_rag, docs = self._rag_context_builder(data.prompt)
        rag_used = bool(docs)
        record_chat_rag_usage(context=self.name, used=rag_used, documents_count=len(docs))
        prompt = (
            "Voce e um assistente de receitas saudaveis. Sugira 3 opcoes objetivas com ingredientes e modo de preparo.\n\n"
            f"Contexto nutricional:\n{contexto_rag}\n\n"
            f"Pedido do usuario:\n{data.prompt}"
        )
        resposta = self._client.generate_text(model=self._settings.openai_model, prompt=prompt)
        warnings = []
        if not docs:
            warnings.append("Receitas sugeridas sem base RAG especifica.")
        self._logger.info(
            "chat_tool.buscar_receitas.completed",
            extra={
                "rag_usado": rag_used,
                "rag_docs_count": len(docs),
                "warnings": len(warnings),
            },
        )
        return ChatToolExecutionOutput(
            tool_name=self.name,
            status="parcial" if warnings else "sucesso",
            resposta=resposta,
            warnings=warnings,
            precisa_revisao=bool(warnings),
            metadados={"documentos_rag": _to_rag_metadata(docs)},
        )


class SugerirSubstituicoesTool:
    name: ChatToolName = "sugerir_substituicoes"

    def __init__(
        self,
        *,
        settings: Settings,
        client: OpenAIClient,
        rag_context_builder: Callable[[str], tuple[str, list[Document]]] | None = None,
        rag_retriever: Callable[[str], list[Document]] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        if rag_context_builder is not None:
            self._rag_context_builder = rag_context_builder
        elif rag_retriever is not None:
            self._rag_context_builder = _build_context_from_retriever(rag_retriever)
        else:
            self._rag_context_builder = build_context_for_query
        self._logger = logging.getLogger(__name__)

    def execute(self, *, data: ChatToolExecutionInput) -> ChatToolExecutionOutput:
        _ensure_openai_api_key(self._settings)
        self._logger.info("chat_tool.sugerir_substituicoes.started")
        contexto_rag, docs = self._rag_context_builder(data.prompt)
        rag_used = bool(docs)
        record_chat_rag_usage(context=self.name, used=rag_used, documents_count=len(docs))
        prompt = (
            "Voce sugere substituicoes alimentares mantendo equilibrio de macros. "
            "Retorne alternativas praticas e quando usar cada uma.\n\n"
            f"Contexto nutricional:\n{contexto_rag}\n\n"
            f"Pedido do usuario:\n{data.prompt}"
        )
        resposta = self._client.generate_text(model=self._settings.openai_model, prompt=prompt)
        warnings = []
        if not docs:
            warnings.append("Substituicoes sugeridas sem base RAG especifica.")
        self._logger.info(
            "chat_tool.sugerir_substituicoes.completed",
            extra={
                "rag_usado": rag_used,
                "rag_docs_count": len(docs),
                "warnings": len(warnings),
            },
        )
        return ChatToolExecutionOutput(
            tool_name=self.name,
            status="parcial" if warnings else "sucesso",
            resposta=resposta,
            warnings=warnings,
            precisa_revisao=bool(warnings),
            metadados={"documentos_rag": _to_rag_metadata(docs)},
        )


class CadastrarPratoTool:
    name: ChatToolName = "cadastrar_prato"

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def execute(self, *, data: ChatToolExecutionInput) -> ChatToolExecutionOutput:
        self._logger.info("chat_tool.cadastrar_prato.started")
        nome_prato = _extract_nome_prato(data.prompt)
        itens = _extract_itens_prato(data.prompt)
        warnings: list[str] = []
        if nome_prato is None:
            warnings.append("Nome do prato nao identificado com clareza.")
        if not itens:
            warnings.append("Itens do prato nao identificados; revise antes de salvar.")

        resposta = (
            "Cadastro de prato preparado para confirmacao."
            if not warnings
            else "Rascunho de cadastro montado; revise os campos antes de confirmar."
        )
        return ChatToolExecutionOutput(
            tool_name=self.name,
            status="parcial" if warnings else "sucesso",
            resposta=resposta,
            warnings=warnings,
            precisa_revisao=bool(warnings),
            metadados={
                "prato": {
                    "nome_prato": nome_prato,
                    "itens": itens,
                }
            },
        )


class ConsultarConhecimentoNutricionalTool:
    name: ChatToolName = "consultar_conhecimento_nutricional"

    def __init__(
        self,
        *,
        settings: Settings,
        client: OpenAIClient,
        rag_context_builder: Callable[[str], tuple[str, list[Document]]] | None = None,
        rag_retriever: Callable[[str], list[Document]] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        if rag_context_builder is not None:
            self._rag_context_builder = rag_context_builder
        elif rag_retriever is not None:
            self._rag_context_builder = _build_context_from_retriever(rag_retriever)
        else:
            self._rag_context_builder = build_context_for_query
        self._logger = logging.getLogger(__name__)

    def execute(self, *, data: ChatToolExecutionInput) -> ChatToolExecutionOutput:
        _ensure_openai_api_key(self._settings)
        self._logger.info("chat_tool.consultar_conhecimento.started")
        contexto_rag, docs = self._rag_context_builder(data.prompt)
        rag_used = bool(docs)
        record_chat_rag_usage(context=self.name, used=rag_used, documents_count=len(docs))
        prompt = (
            "Voce responde perguntas nutricionais com linguagem clara e direta, destacando limites quando houver.\n\n"
            f"Contexto nutricional:\n{contexto_rag}\n\n"
            f"Pergunta do usuario:\n{data.prompt}"
        )
        resposta = self._client.generate_text(model=self._settings.openai_model, prompt=prompt)
        warnings = []
        if not docs:
            warnings.append("Consulta respondida sem documentos de base.")
        self._logger.info(
            "chat_tool.consultar_conhecimento.completed",
            extra={
                "rag_usado": rag_used,
                "rag_docs_count": len(docs),
                "warnings": len(warnings),
            },
        )
        return ChatToolExecutionOutput(
            tool_name=self.name,
            status="parcial" if warnings else "sucesso",
            resposta=resposta,
            warnings=warnings,
            precisa_revisao=bool(warnings),
            metadados={"documentos_rag": _to_rag_metadata(docs)},
        )


def _ensure_openai_api_key(settings: Settings) -> None:
    if not settings.openai_api_key.strip():
        raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)


def _extract_peso_kg(prompt: str) -> float | None:
    match = re.search(r"(\d{2,3}(?:[.,]\d+)?)\s*(?:kg|quilo|quilos)\b", prompt.lower())
    if not match:
        return None
    return _to_float(match.group(1))


def _extract_altura_m(prompt: str) -> float | None:
    prompt_lower = prompt.lower()
    match_m = re.search(r"(\d(?:[.,]\d{1,2}))\s*m\b", prompt_lower)
    if match_m:
        return _to_float(match_m.group(1))
    match_cm = re.search(r"(\d{3})\s*cm\b", prompt_lower)
    if match_cm:
        altura_cm = _to_float(match_cm.group(1))
        if altura_cm is None:
            return None
        return round(altura_cm / 100.0, 4)
    return None


def _classificar_imc(imc: float) -> str:
    if imc < 18.5:
        return "baixo peso"
    if imc < 25:
        return "peso adequado"
    if imc < 30:
        return "sobrepeso"
    if imc < 35:
        return "obesidade grau I"
    if imc < 40:
        return "obesidade grau II"
    return "obesidade grau III"


def _extract_nome_prato(prompt: str) -> str | None:
    match = re.search(r"(?i)(?:prato|receita)\s*[:\-]\s*([^\n,;]+)", prompt)
    if match:
        nome = match.group(1).strip()
        return nome if nome else None
    return None


def _extract_itens_prato(prompt: str) -> list[str]:
    if ":" in prompt:
        right = prompt.split(":", 1)[1]
    else:
        right = prompt
    parts = re.split(r",|;|\+", right)
    itens = [part.strip() for part in parts if part.strip()]
    return itens[:15]


def _to_float(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _build_context_from_retriever(
    retriever: Callable[[str], list[Document]],
) -> Callable[[str], tuple[str, list[Document]]]:
    def _inner(query: str) -> tuple[str, list[Document]]:
        docs = retriever(query)
        return _format_rag_context(docs), docs

    return _inner


def _format_rag_context(documentos: list[Document]) -> str:
    if not documentos:
        return "Sem documentos de base."
    chunks: list[str] = []
    for index, doc in enumerate(documentos[:4], start=1):
        source = str(doc.metadata.get("source_path") or doc.metadata.get("source") or "desconhecido")
        chunks.append(f"[doc_{index} source={source}] {doc.page_content}")
    return "\n".join(chunks).strip()


def _to_rag_metadata(documentos: list[Document]) -> list[dict[str, str | int | None]]:
    metadata: list[dict[str, str | int | None]] = []
    for index, doc in enumerate(documentos[:6], start=1):
        source = str(doc.metadata.get("source_path") or doc.metadata.get("source") or "")
        metadata.append(
            {
                "rank": index,
                "source": source or None,
                "snippet_chars": len(doc.page_content),
            }
        )
    return metadata
