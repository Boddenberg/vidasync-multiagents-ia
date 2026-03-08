from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from vidasync_multiagents_ia.schemas import IntencaoChatDetectada

ChatToolStatus = Literal["sucesso", "parcial", "erro"]
ChatToolName = Literal[
    "calcular_calorias",
    "calcular_macros",
    "calcular_imc",
    "buscar_receitas",
    "sugerir_substituicoes",
    "cadastrar_prato",
    "consultar_conhecimento_nutricional",
]


@dataclass(slots=True)
class ChatToolExecutionInput:
    tool_name: ChatToolName
    prompt: str
    idioma: str
    intencao: IntencaoChatDetectada
    metadados: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChatToolExecutionOutput:
    tool_name: ChatToolName
    status: ChatToolStatus
    resposta: str
    warnings: list[str] = field(default_factory=list)
    precisa_revisao: bool = False
    metadados: dict[str, Any] = field(default_factory=dict)


class ChatTool(Protocol):
    name: ChatToolName

    # /**** Contrato padrao de tool: entrada textual + contexto e saida estruturada para o roteador. ****/
    def execute(self, *, data: ChatToolExecutionInput) -> ChatToolExecutionOutput:
        ...
