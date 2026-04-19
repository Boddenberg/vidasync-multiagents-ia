import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.documents import Document

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import record_chat_rag_usage
from vidasync_multiagents_ia.rag.vector_store import build_context_for_query


@dataclass(slots=True)
class ChatReceitasFlowOutput:
    resposta: str
    warnings: list[str] = field(default_factory=list)
    precisa_revisao: bool = False
    metadados: dict[str, Any] = field(default_factory=dict)


class ChatReceitasFlowService:
    """
    /****
     * Fluxo dedicado de receitas no chat conversacional.
     *
     * Etapas:
     * 1) entende perfil do pedido (preferencias/restricoes/objetivo/contexto)
     * 2) recupera suporte de conhecimento via RAG
     * 3) gera sugestoes praticas e organizadas de receitas
     *
     * Consideracoes:
     * - Mantem regras deterministicas fora deste fluxo.
     * - Retorna metadados ricos para auditoria e evolucao futura com judges.
     ****/
    """

    def __init__(
        self,
        *,
        settings: Settings,
        client: OpenAIClient | None = None,
        rag_context_builder: Callable[[str], tuple[str, list[Document]]] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._rag_context_builder = rag_context_builder or build_context_for_query
        self._logger = logging.getLogger(__name__)

    def executar(self, *, prompt: str, idioma: str = "pt-BR") -> ChatReceitasFlowOutput:
        self._ensure_openai_api_key()
        pedido = prompt.strip()
        if not pedido:
            raise ServiceError("Pedido de receita vazio.", status_code=400)

        self._logger.info(
            "chat_receitas_flow.started",
            extra={"idioma": idioma, "prompt_chars": len(pedido), "modelo": self._settings.openai_model},
        )

        warnings: list[str] = []
        profile_payload, profile_by_fallback = self._extract_profile(prompt=pedido, idioma=idioma)
        if profile_by_fallback:
            warnings.append("Perfil de receitas extraido por fallback heuristico; revise preferencias e restricoes.")

        rag_query = _build_rag_query(prompt=pedido, profile=profile_payload)
        rag_context, rag_docs = self._rag_context_builder(rag_query)
        rag_used = bool(rag_docs)
        record_chat_rag_usage(context="chat_receitas_flow", used=rag_used, documents_count=len(rag_docs))
        if not rag_docs:
            warnings.append("Base RAG sem documentos relevantes para este pedido; resposta gerada com contexto limitado.")

        receitas_payload = self._generate_recipe_suggestions(
            prompt=pedido,
            idioma=idioma,
            profile=profile_payload,
            rag_context=rag_context,
        )
        receitas = _normalize_recipes(receitas_payload.get("receitas"))
        if not receitas:
            warnings.append("Nao foi possivel estruturar receitas suficientes para este pedido.")

        resposta = _format_recipes_response(
            profile=profile_payload,
            receitas=receitas,
            dicas=_to_clean_list(receitas_payload.get("dicas_preparo")),
            lista_compras=_to_clean_list(receitas_payload.get("lista_compras")),
            observacoes=_to_clean_list(receitas_payload.get("observacoes")),
        )

        precisa_revisao = bool(warnings) or len(receitas) == 0
        metadados = {
            "flow": "receitas_personalizadas_v1",
            "perfil": profile_payload,
            "receitas": receitas,
            "documentos_rag": _to_rag_metadata(rag_docs),
            "fontes_rag": len(rag_docs),
            "rag_used": rag_used,
            "rag_documents_count": len(rag_docs),
        }
        self._logger.info(
            "chat_receitas_flow.completed",
            extra={
                "warnings": len(warnings),
                "receitas": len(receitas),
                "fontes_rag": len(rag_docs),
                "rag_usado": rag_used,
                "precisa_revisao": precisa_revisao,
            },
        )
        return ChatReceitasFlowOutput(
            resposta=resposta,
            warnings=warnings,
            precisa_revisao=precisa_revisao,
            metadados=metadados,
        )

    def _extract_profile(self, *, prompt: str, idioma: str) -> tuple[dict[str, Any], bool]:
        system_prompt = (
            "Voce extrai perfil de preferencia alimentar para recomendacao de receitas. "
            "Retorne somente JSON valido sem markdown."
        )
        user_prompt = (
            f"Idioma: {idioma}. Extraia do texto os campos abaixo e responda em JSON:\n"
            "{"
            '"preferencias": ["..."],'
            '"restricoes": ["..."],'
            '"objetivo_nutricional": "texto ou null",'
            '"contexto_refeicao": "texto ou null",'
            '"ingredientes_disponiveis": ["..."],'
            '"tempo_max_preparo_min": numero ou null,'
            '"observacoes_usuario": "texto ou null"'
            "}\n\n"
            f"Texto:\n{prompt}"
        )
        try:
            payload = self._client.generate_json_from_text(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            normalized = _normalize_profile(payload)
            return normalized, False
        except Exception:  # noqa: BLE001
            self._logger.exception("chat_receitas_flow.profile_extract_failed")
            return _extract_profile_fallback(prompt), True

    def _generate_recipe_suggestions(
        self,
        *,
        prompt: str,
        idioma: str,
        profile: dict[str, Any],
        rag_context: str,
    ) -> dict[str, Any]:
        system_prompt = (
            "Voce monta sugestoes praticas de receitas personalizadas para contexto nutricional. "
            "Responda somente JSON valido sem markdown."
        )
        user_prompt = (
            f"Idioma: {idioma}.\n"
            "Use o perfil e o contexto para sugerir ate 3 receitas claras e praticas.\n"
            "Retorne JSON com estrutura:\n"
            "{"
            '"receitas":[{'
            '"nome":"",'
            '"motivo_aderencia":"",'
            '"tempo_preparo_min":0,'
            '"rendimento_porcoes":"",'
            '"ingredientes":[""],'
            '"preparo_passos":[""],'
            '"ajuste_objetivo":""'
            "}],"
            '"dicas_preparo":[""],'
            '"lista_compras":[""],'
            '"observacoes":[""]'
            "}\n\n"
            f"Perfil:\n{profile}\n\n"
            f"Contexto RAG:\n{rag_context or 'Sem contexto adicional.'}\n\n"
            f"Pedido do usuario:\n{prompt}"
        )
        payload = self._client.generate_json_from_text(
            model=self._settings.openai_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return payload if isinstance(payload, dict) else {}

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)


def _normalize_profile(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "preferencias": _to_clean_list(payload.get("preferencias")),
        "restricoes": _to_clean_list(payload.get("restricoes")),
        "objetivo_nutricional": _to_optional_str(payload.get("objetivo_nutricional")),
        "contexto_refeicao": _to_optional_str(payload.get("contexto_refeicao")),
        "ingredientes_disponiveis": _to_clean_list(payload.get("ingredientes_disponiveis")),
        "tempo_max_preparo_min": _to_optional_int(payload.get("tempo_max_preparo_min")),
        "observacoes_usuario": _to_optional_str(payload.get("observacoes_usuario")),
    }


def _extract_profile_fallback(prompt: str) -> dict[str, Any]:
    lower = _normalize_match_text(prompt)
    restricoes: list[str] = []
    for termo in ("sem lactose", "sem gluten", "vegano", "vegetariano", "sem acucar", "sem aÃ§Ãºcar"):
        if termo in lower:
            restricoes.append(termo)
    objetivo = None
    if "emagrec" in lower:
        objetivo = "emagrecimento"
    elif "ganho de massa" in lower or "hipertrof" in lower:
        objetivo = "ganho de massa"
    elif "manter peso" in lower:
        objetivo = "manutencao de peso"
    tempo = None
    match_min = re.search(r"(\d{1,3})\s*min", lower)
    if match_min:
        tempo = int(match_min.group(1))
    return {
        "preferencias": [],
        "restricoes": restricoes,
        "objetivo_nutricional": objetivo,
        "contexto_refeicao": None,
        "ingredientes_disponiveis": [],
        "tempo_max_preparo_min": tempo,
        "observacoes_usuario": None,
    }


def _normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()


def _build_rag_query(*, prompt: str, profile: dict[str, Any]) -> str:
    parts = [prompt.strip()]
    if profile.get("objetivo_nutricional"):
        parts.append(f"objetivo: {profile['objetivo_nutricional']}")
    if profile.get("restricoes"):
        parts.append(f"restricoes: {', '.join(profile['restricoes'])}")
    if profile.get("preferencias"):
        parts.append(f"preferencias: {', '.join(profile['preferencias'])}")
    return " | ".join(part for part in parts if part)


def _normalize_recipes(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    receitas: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        nome = _to_optional_str(item.get("nome"))
        if not nome:
            continue
        receita = {
            "nome": nome,
            "motivo_aderencia": _to_optional_str(item.get("motivo_aderencia")),
            "tempo_preparo_min": _to_optional_int(item.get("tempo_preparo_min")),
            "rendimento_porcoes": _to_optional_str(item.get("rendimento_porcoes")),
            "ingredientes": _to_clean_list(item.get("ingredientes")),
            "preparo_passos": _to_clean_list(item.get("preparo_passos")),
            "ajuste_objetivo": _to_optional_str(item.get("ajuste_objetivo")),
        }
        receitas.append(receita)
    return receitas[:3]


def _format_recipes_response(
    *,
    profile: dict[str, Any],
    receitas: list[dict[str, Any]],
    dicas: list[str],
    lista_compras: list[str],
    observacoes: list[str],
) -> str:
    if not receitas:
        return (
            "Nao consegui montar receitas completas com seguranca a partir deste pedido. "
            "Me diga seu objetivo, restricoes e refeicao alvo para ajustar melhor."
        )

    linhas: list[str] = ["Sugestao de receitas personalizada:"]
    perfil_partes: list[str] = []
    if profile.get("objetivo_nutricional"):
        perfil_partes.append(f"objetivo: {profile['objetivo_nutricional']}")
    if profile.get("restricoes"):
        perfil_partes.append(f"restricoes: {', '.join(profile['restricoes'])}")
    if profile.get("preferencias"):
        perfil_partes.append(f"preferencias: {', '.join(profile['preferencias'])}")
    if perfil_partes:
        linhas.append(f"Perfil considerado: {' | '.join(perfil_partes)}")

    for index, receita in enumerate(receitas, start=1):
        linhas.append(f"{index}. {receita['nome']}")
        if receita.get("motivo_aderencia"):
            linhas.append(f"Motivo: {receita['motivo_aderencia']}")
        if receita.get("tempo_preparo_min") is not None:
            linhas.append(f"Tempo: {receita['tempo_preparo_min']} min")
        if receita.get("ingredientes"):
            linhas.append("Ingredientes: " + ", ".join(receita["ingredientes"]))
        if receita.get("preparo_passos"):
            passos = "; ".join(receita["preparo_passos"][:4])
            linhas.append(f"Preparo: {passos}")
        if receita.get("ajuste_objetivo"):
            linhas.append(f"Ajuste nutricional: {receita['ajuste_objetivo']}")

    if dicas:
        linhas.append("Dicas praticas: " + "; ".join(dicas[:4]))
    if lista_compras:
        linhas.append("Lista de compras enxuta: " + ", ".join(lista_compras[:8]))
    if observacoes:
        linhas.append("Observacoes: " + "; ".join(observacoes[:3]))

    return "\n".join(linhas).strip()


def _to_clean_list(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            output.append(text)
    return output[:12]


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        match = re.search(r"\d{1,4}", value)
        if match:
            return int(match.group(0))
    return None


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

