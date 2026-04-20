"""Contratos da frente dedicada de chat nutricional."""

from vidasync_multiagents_ia.schemas.openai_chat import OpenAIChatRequest, OpenAIChatResponse


class NutriChatRequest(OpenAIChatRequest):
    """Mantem o mesmo contrato do chat atual para evitar duplicacao desnecessaria."""


class NutriChatResponse(OpenAIChatResponse):
    """Resposta da frente de chat dedicada a nutricao e alimentacao."""


__all__ = ["NutriChatRequest", "NutriChatResponse"]
