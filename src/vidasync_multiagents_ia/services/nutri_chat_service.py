import logging
import unicodedata
from time import perf_counter
from typing import Any

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.observability.payload_preview import preview_text
from vidasync_multiagents_ia.schemas import NutriChatResponse
from vidasync_multiagents_ia.services.openai_chat_service import OpenAIChatService

_SHORT_GREETINGS = {
    "oi",
    "ola",
    "bom dia",
    "boa tarde",
    "boa noite",
    "tudo bem",
    "e ai",
}

_NUTRITION_SCOPE_KEYWORDS = {
    "alimentacao",
    "alimento",
    "alimentos",
    "almoco",
    "beber agua",
    "caloria",
    "calorias",
    "carbo",
    "carboidrato",
    "carboidratos",
    "cafe da manha",
    "ceia",
    "comer",
    "comida",
    "dieta",
    "emagrecer",
    "emagrecimento",
    "fibra",
    "fibras",
    "gordura",
    "gorduras",
    "gramas",
    "hidratar",
    "hidratacao",
    "imc",
    "jantar",
    "kcal",
    "lanche",
    "macro",
    "macros",
    "massa muscular",
    "nutri",
    "nutricao",
    "peso",
    "plano alimentar",
    "porcao",
    "porcoes",
    "proteina",
    "proteinas",
    "receita",
    "receitas",
    "refeicao",
    "refeicoes",
    "saudavel",
    "substituicao",
    "substituicoes",
    "suplementacao",
    "suplemento",
    "tbca",
    "taco",
    "whey",
}


class NutriChatService:
    _OUT_OF_SCOPE_RESPONSE = (
        "Posso ajudar com alimentacao, calorias, macros, receitas, substituicoes, "
        "refeicoes, IMC e plano alimentar. Se quiser, me diga sua duvida nutricional."
    )

    def __init__(
        self,
        *,
        settings: Settings,
        openai_chat_service: OpenAIChatService | None = None,
    ) -> None:
        self._settings = settings
        self._openai_chat_service = openai_chat_service or OpenAIChatService(settings=settings)
        self._logger = logging.getLogger(__name__)

    def chat(
        self,
        prompt: str,
        *,
        conversation_id: str | None = None,
        usar_memoria: bool = True,
        metadados_conversa: dict[str, str] | None = None,
        plano_anexo: dict[str, Any] | None = None,
        refeicao_anexo: dict[str, Any] | None = None,
    ) -> NutriChatResponse:
        started = perf_counter()
        self._logger.info(
            "nutri_chat.started",
            extra={
                "conversation_id": conversation_id,
                "prompt_chars": len(prompt),
                "usar_memoria": usar_memoria,
                "plano_anexo_presente": bool(plano_anexo),
                "refeicao_anexo_presente": bool(refeicao_anexo),
                "prompt_preview": preview_text(
                    prompt,
                    max_chars=self._settings.log_internal_max_body_chars,
                )
                if self._settings.log_internal_payloads
                else None,
            },
        )

        if not _is_nutrition_scope(
            prompt,
            plano_anexo=plano_anexo,
            refeicao_anexo=refeicao_anexo,
        ):
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.info(
                "nutri_chat.scope_blocked",
                extra={
                    "conversation_id": conversation_id,
                    "fora_do_escopo": True,
                    "duration_ms": round(duration_ms, 4),
                },
            )
            return NutriChatResponse(
                model=self._settings.openai_model,
                response=self._OUT_OF_SCOPE_RESPONSE,
                conversation_id=conversation_id,
            )

        try:
            output = self._openai_chat_service.chat(
                prompt,
                conversation_id=conversation_id,
                usar_memoria=usar_memoria,
                metadados_conversa=metadados_conversa,
                plano_anexo=plano_anexo,
                refeicao_anexo=refeicao_anexo,
            )
        except Exception as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.exception(
                "nutri_chat.failed",
                extra={
                    "conversation_id": conversation_id,
                    "fora_do_escopo": False,
                    "duration_ms": round(duration_ms, 4),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise

        duration_ms = (perf_counter() - started) * 1000.0
        self._logger.info(
            "nutri_chat.completed",
            extra={
                "conversation_id": output.conversation_id,
                "intencao_detectada": output.intencao_detectada.intencao if output.intencao_detectada else None,
                "pipeline": output.roteamento.pipeline if output.roteamento else None,
                "handler": output.roteamento.handler if output.roteamento else None,
                "status": output.roteamento.status if output.roteamento else "sucesso",
                "fora_do_escopo": False,
                "duration_ms": round(duration_ms, 4),
            },
        )
        return NutriChatResponse(**output.model_dump())


def _is_nutrition_scope(
    prompt: str,
    *,
    plano_anexo: dict[str, Any] | None,
    refeicao_anexo: dict[str, Any] | None,
) -> bool:
    if plano_anexo or refeicao_anexo:
        return True

    normalized = _normalize_text(prompt)
    if not normalized:
        return False
    if normalized in _SHORT_GREETINGS:
        return True
    return any(keyword in normalized for keyword in _NUTRITION_SCOPE_KEYWORDS)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.lower().split())


__all__ = ["NutriChatService"]
