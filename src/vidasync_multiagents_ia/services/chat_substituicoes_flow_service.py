import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.documents import Document

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import record_chat_rag_usage
from vidasync_multiagents_ia.rag.vector_store import build_context_for_query
from vidasync_multiagents_ia.schemas import IntencaoChatDetectada
from vidasync_multiagents_ia.services.chat_tools import ChatToolExecutionInput, ChatToolExecutionOutput
from vidasync_multiagents_ia.services.chat_tools.nutricao_tools import SugerirSubstituicoesTool


@dataclass(slots=True)
class ChatSubstituicoesFlowOutput:
    resposta: str
    warnings: list[str] = field(default_factory=list)
    precisa_revisao: bool = False
    metadados: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _RuleSubstituicao:
    nome: str
    equivalencia: str
    quando_usar: str
    tags: tuple[str, ...] = ()


class ChatSubstituicoesFlowService:
    """
    /****
     * Fluxo dedicado de substituicoes alimentares.
     *
     * Estrategia:
     * 1) entende alimento original, objetivo e contexto do pedido
     * 2) aplica regras deterministicas de equivalencia alimentar
     * 3) aciona tool contextual de substituicoes quando faltam opcoes robustas
     *
     * Evolucao futura:
     * - plugar base personalizada por usuario (preferencias, historico, exames)
     * - calibrar equivalencias por porcao real e metas individuais
     ****/
    """

    def __init__(
        self,
        *,
        settings: Settings,
        client: OpenAIClient | None = None,
        rag_context_builder: Callable[[str], tuple[str, list[Document]]] | None = None,
        tool_runner: Callable[[str, str], ChatToolExecutionOutput] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._rag_context_builder = rag_context_builder or build_context_for_query
        self._tool = SugerirSubstituicoesTool(
            settings=settings,
            client=self._client,
            rag_context_builder=self._rag_context_builder,
        )
        self._tool_runner = tool_runner or self._run_tool_substituicoes
        self._logger = logging.getLogger(__name__)

    def executar(self, *, prompt: str, idioma: str = "pt-BR") -> ChatSubstituicoesFlowOutput:
        self._ensure_openai_api_key()
        pedido = prompt.strip()
        if not pedido:
            raise ServiceError("Pedido de substituicao vazio.", status_code=400)

        self._logger.info(
            "chat_substituicoes_flow.started",
            extra={"idioma": idioma, "prompt_chars": len(pedido), "modelo": self._settings.openai_model},
        )
        warnings: list[str] = []

        profile, by_fallback = self._extract_profile(prompt=pedido, idioma=idioma)
        if by_fallback:
            warnings.append("Perfil de substituicao extraido por fallback heuristico; revise alimento e objetivo.")

        alimento_original = _to_optional_str(profile.get("alimento_original"))
        objetivo_troca = _to_optional_str(profile.get("objetivo_troca"))
        restricoes = _to_clean_list(profile.get("restricoes"))
        contexto_refeicao = _to_optional_str(profile.get("contexto_refeicao"))

        substituicoes_regra = _build_rule_substitutions(
            alimento_original=alimento_original,
            objetivo_troca=objetivo_troca,
            restricoes=restricoes,
        )
        usar_tool = _should_use_tool_fallback(
            alimento_original=alimento_original,
            objetivo_troca=objetivo_troca,
            substituicoes_regra=substituicoes_regra,
        )

        tool_output: ChatToolExecutionOutput | None = None
        rag_docs_count = 0
        rag_used = False
        if usar_tool:
            tool_output = self._tool_runner(pedido, idioma)
            if tool_output.warnings:
                warnings.extend(tool_output.warnings)
            docs = tool_output.metadados.get("documentos_rag")
            if isinstance(docs, list):
                rag_docs_count = len(docs)
                rag_used = rag_docs_count > 0
            record_chat_rag_usage(
                context="chat_substituicoes_flow",
                used=rag_used,
                documents_count=rag_docs_count,
            )

        if not alimento_original:
            warnings.append("Nao foi possivel identificar claramente o alimento original da troca.")
        if not substituicoes_regra and tool_output is None:
            warnings.append("Nao foram encontradas substituicoes coerentes para este pedido.")

        resposta = _format_substituicoes_response(
            alimento_original=alimento_original,
            objetivo_troca=objetivo_troca,
            contexto_refeicao=contexto_refeicao,
            substituicoes_regra=substituicoes_regra,
            tool_output=tool_output,
            observacoes=_to_clean_list(profile.get("observacoes_usuario")),
        )
        precisa_revisao = bool(warnings) or (not substituicoes_regra and tool_output is None)
        metadados = {
            "flow": "substituicoes_alimentares_v1",
            "perfil": {
                "alimento_original": alimento_original,
                "objetivo_troca": objetivo_troca,
                "contexto_refeicao": contexto_refeicao,
                "restricoes": restricoes,
                "preferencias": _to_clean_list(profile.get("preferencias")),
                "alimentos_evitar": _to_clean_list(profile.get("alimentos_evitar")),
            },
            "substituicoes_regra": substituicoes_regra,
            "tool_fallback_utilizada": tool_output is not None,
            "tool_fallback": (
                {
                    "status": tool_output.status,
                    "resposta": tool_output.resposta,
                    "warnings": tool_output.warnings,
                    "metadados": tool_output.metadados,
                }
                if tool_output is not None
                else None
            ),
        }
        self._logger.info(
            "chat_substituicoes_flow.completed",
            extra={
                "warnings": len(warnings),
                "substituicoes_regra": len(substituicoes_regra),
                "tool_fallback_utilizada": tool_output is not None,
                "rag_usado": rag_used,
                "rag_docs_count": rag_docs_count,
                "precisa_revisao": precisa_revisao,
            },
        )
        return ChatSubstituicoesFlowOutput(
            resposta=resposta,
            warnings=warnings,
            precisa_revisao=precisa_revisao,
            metadados=metadados,
        )

    def _extract_profile(self, *, prompt: str, idioma: str) -> tuple[dict[str, Any], bool]:
        system_prompt = (
            "Voce extrai perfil para substituicoes alimentares. "
            "Retorne somente JSON valido, sem markdown."
        )
        user_prompt = (
            f"Idioma: {idioma}. Extraia do texto os campos abaixo e responda em JSON:\n"
            "{"
            '"alimento_original":"texto ou null",'
            '"objetivo_troca":"texto ou null",'
            '"contexto_refeicao":"texto ou null",'
            '"restricoes":["..."],'
            '"preferencias":["..."],'
            '"alimentos_evitar":["..."],'
            '"observacoes_usuario":"texto ou null"'
            "}\n\n"
            f"Texto:\n{prompt}"
        )
        try:
            payload = self._client.generate_json_from_text(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            if not isinstance(payload, dict):
                return _extract_profile_fallback(prompt), True
            return payload, False
        except Exception:  # noqa: BLE001
            self._logger.exception("chat_substituicoes_flow.profile_extract_failed")
            return _extract_profile_fallback(prompt), True

    def _run_tool_substituicoes(self, prompt: str, idioma: str) -> ChatToolExecutionOutput:
        intencao = IntencaoChatDetectada(
            intencao="pedir_substituicoes",
            confianca=0.99,
            contexto_roteamento="chat_substituicoes",
            requer_fluxo_estruturado=False,
        )
        return self._tool.execute(
            data=ChatToolExecutionInput(
                tool_name="sugerir_substituicoes",
                prompt=prompt,
                idioma=idioma,
                intencao=intencao,
            )
        )

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)


_RULE_BASE: dict[str, list[_RuleSubstituicao]] = {
    "arroz branco": [
        _RuleSubstituicao(
            nome="arroz integral",
            equivalencia="4 colheres de sopa cozidas",
            quando_usar="quando quiser maior teor de fibras com sabor semelhante",
            tags=("fibra", "saciedade"),
        ),
        _RuleSubstituicao(
            nome="quinoa cozida",
            equivalencia="3 colheres de sopa cozidas",
            quando_usar="quando quiser aumentar densidade nutricional e proteina",
            tags=("proteina", "fibra"),
        ),
        _RuleSubstituicao(
            nome="couve-flor ralada refogada",
            equivalencia="1 xicara cheia",
            quando_usar="quando objetivo for reduzir carboidrato total",
            tags=("baixo_carbo", "emagrecimento"),
        ),
    ],
    "pao frances": [
        _RuleSubstituicao(
            nome="pao integral 100%",
            equivalencia="1 fatia media",
            quando_usar="quando quiser manter praticidade com mais fibras",
            tags=("fibra", "saciedade"),
        ),
        _RuleSubstituicao(
            nome="tapioca com chia",
            equivalencia="2 colheres de sopa de goma + 1 colher de chia",
            quando_usar="quando buscar textura leve e ajuste de recheios",
            tags=("praticidade",),
        ),
        _RuleSubstituicao(
            nome="omelete simples",
            equivalencia="2 ovos",
            quando_usar="quando objetivo for aumentar proteina no cafe da manha",
            tags=("proteina", "ganho_massa"),
        ),
    ],
    "leite integral": [
        _RuleSubstituicao(
            nome="leite semidesnatado",
            equivalencia="1 copo (200 ml)",
            quando_usar="quando quiser reduzir gordura mantendo leite animal",
            tags=("emagrecimento",),
        ),
        _RuleSubstituicao(
            nome="bebida vegetal sem acucar",
            equivalencia="1 copo (200 ml)",
            quando_usar="quando houver restricao a lactose",
            tags=("sem_lactose",),
        ),
        _RuleSubstituicao(
            nome="iogurte natural sem lactose",
            equivalencia="1 pote (170 g)",
            quando_usar="quando desejar maior saciedade e cremosidade",
            tags=("sem_lactose", "proteina"),
        ),
    ],
    "refrigerante": [
        _RuleSubstituicao(
            nome="agua com gas e limao",
            equivalencia="1 copo (300 ml)",
            quando_usar="quando quiser reduzir acucar e manter sensacao gaseificada",
            tags=("emagrecimento", "sem_acucar"),
        ),
        _RuleSubstituicao(
            nome="cha gelado sem acucar",
            equivalencia="1 copo (300 ml)",
            quando_usar="quando quiser variar sabor sem calorias extras",
            tags=("sem_acucar",),
        ),
        _RuleSubstituicao(
            nome="agua saborizada natural",
            equivalencia="1 copo (300 ml)",
            quando_usar="quando foco for hidratacao no dia a dia",
            tags=("hidratacao",),
        ),
    ],
}

_ALIASES: dict[str, str] = {
    "arroz": "arroz branco",
    "arroz branco": "arroz branco",
    "pao": "pao frances",
    "pao frances": "pao frances",
    "leite": "leite integral",
    "leite integral": "leite integral",
    "refrigerante": "refrigerante",
    "refri": "refrigerante",
}


def _extract_profile_fallback(prompt: str) -> dict[str, Any]:
    text = prompt.lower()
    alimento = _extract_alimento_original_by_regex(text)
    objetivo = None
    if "emagrec" in text or "perder peso" in text:
        objetivo = "emagrecimento"
    elif "ganho de massa" in text or "hipertrof" in text:
        objetivo = "ganho de massa"
    elif "manter peso" in text:
        objetivo = "manutencao de peso"

    restricoes: list[str] = []
    for termo in ("sem lactose", "sem gluten", "sem acucar", "vegano", "vegetariano"):
        if termo in text:
            restricoes.append(termo)

    return {
        "alimento_original": alimento,
        "objetivo_troca": objetivo,
        "contexto_refeicao": None,
        "restricoes": restricoes,
        "preferencias": [],
        "alimentos_evitar": [],
        "observacoes_usuario": None,
    }


def _extract_alimento_original_by_regex(text: str) -> str | None:
    match = re.search(r"(?:trocar|substituir)\s+(?:o|a|um|uma)?\s*([a-z0-9 ]{3,40})\s+(?:por|pra|para)\b", text)
    if match:
        return match.group(1).strip()
    for alias in _ALIASES:
        if alias in text:
            return alias
    return None


def _canonicalize_alimento(value: str | None) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.lower().split())
    if normalized in _ALIASES:
        return _ALIASES[normalized]
    for alias, canonical in _ALIASES.items():
        if alias in normalized:
            return canonical
    return normalized


def _build_rule_substitutions(
    *,
    alimento_original: str | None,
    objetivo_troca: str | None,
    restricoes: list[str],
) -> list[dict[str, str]]:
    canonical = _canonicalize_alimento(alimento_original)
    if not canonical:
        return []
    options = _RULE_BASE.get(canonical, [])
    if not options:
        return []

    restricoes_norm = {item.lower() for item in restricoes}
    objetivo_norm = (objetivo_troca or "").lower()
    output: list[dict[str, str]] = []
    for option in options:
        if "sem lactose" in restricoes_norm and "sem_lactose" not in option.tags and "lactose" in option.nome:
            continue
        if "sem acucar" in restricoes_norm and "sem_acucar" not in option.tags and "acucar" in option.nome:
            continue
        prioridade = "media"
        if "emagrec" in objetivo_norm and ("emagrecimento" in option.tags or "baixo_carbo" in option.tags):
            prioridade = "alta"
        if ("ganho de massa" in objetivo_norm or "hipertrof" in objetivo_norm) and "proteina" in option.tags:
            prioridade = "alta"
        output.append(
            {
                "alimento_substituto": option.nome,
                "equivalencia": option.equivalencia,
                "quando_usar": option.quando_usar,
                "prioridade": prioridade,
            }
        )
    output.sort(key=lambda item: 0 if item["prioridade"] == "alta" else 1)
    return output[:4]


def _should_use_tool_fallback(
    *,
    alimento_original: str | None,
    objetivo_troca: str | None,
    substituicoes_regra: list[dict[str, str]],
) -> bool:
    if not alimento_original:
        return True
    if len(substituicoes_regra) < 2:
        return True
    if not objetivo_troca:
        return True
    return False


def _format_substituicoes_response(
    *,
    alimento_original: str | None,
    objetivo_troca: str | None,
    contexto_refeicao: str | None,
    substituicoes_regra: list[dict[str, str]],
    tool_output: ChatToolExecutionOutput | None,
    observacoes: list[str],
) -> str:
    if not substituicoes_regra and tool_output is None:
        return (
            "Nao consegui sugerir substituicoes confiaveis com os dados atuais. "
            "Me diga qual alimento voce quer trocar, objetivo da troca e suas restricoes."
        )

    lines: list[str] = ["Plano de substituicoes alimentares:"]
    if alimento_original:
        lines.append(f"Alimento original: {alimento_original}")
    if objetivo_troca:
        lines.append(f"Objetivo da troca: {objetivo_troca}")
    if contexto_refeicao:
        lines.append(f"Contexto: {contexto_refeicao}")

    if substituicoes_regra:
        lines.append("Substituicoes sugeridas (regra + coerencia nutricional):")
        for index, item in enumerate(substituicoes_regra, start=1):
            lines.append(
                f"{index}. {item['alimento_substituto']} | Equivalencia: {item['equivalencia']} | Quando usar: {item['quando_usar']}"
            )

    if tool_output is not None:
        lines.append("Complemento contextual (tool):")
        lines.append(tool_output.resposta.strip())

    if observacoes:
        lines.append("Observacoes do pedido: " + "; ".join(observacoes[:3]))

    lines.append("Se quiser, eu ajusto as opcoes para cafe da manha, almoco, jantar ou lanche.")
    return "\n".join(lines).strip()


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_clean_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            output.append(text)
    return output[:12]

