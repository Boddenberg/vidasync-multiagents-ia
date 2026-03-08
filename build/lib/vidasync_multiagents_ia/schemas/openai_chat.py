from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

IntencaoChatNome = Literal[
    "enviar_plano_nutri",
    "pedir_receitas",
    "pedir_substituicoes",
    "pedir_dicas",
    "perguntar_calorias",
    "cadastrar_pratos",
    "calcular_imc",
    "registrar_refeicao_foto",
    "registrar_refeicao_audio",
    "conversa_geral",
]

ChatPipelineNome = Literal[
    "rag_conhecimento_nutricional",
    "tool_calculo",
    "pipeline_plano_alimentar",
    "cadastro_refeicoes",
    "cadastro_pratos",
    "resposta_conversacional_geral",
]


class IntencaoChatCandidata(BaseModel):
    intencao: IntencaoChatNome
    confianca: float = Field(ge=0, le=1)


class IntencaoChatDetectada(BaseModel):
    intencao: IntencaoChatNome
    confianca: float = Field(ge=0, le=1)
    contexto_roteamento: str
    requer_fluxo_estruturado: bool = False
    metodo: str = "heuristico_keywords_v1"
    candidatos: list[IntencaoChatCandidata] = Field(default_factory=list)


class ChatPlanoAnexoInput(BaseModel):
    tipo_fonte: Literal["imagem", "pdf"]
    imagem_url: str | None = None
    pdf_base64: str | None = None
    nome_arquivo: str | None = None
    executar_ocr_literal: bool = True

    @model_validator(mode="after")
    def _validate_payload(self) -> "ChatPlanoAnexoInput":
        if self.tipo_fonte == "imagem" and not (self.imagem_url and self.imagem_url.strip()):
            raise ValueError("Campo 'imagem_url' e obrigatorio quando tipo_fonte='imagem'.")
        if self.tipo_fonte == "pdf" and not (self.pdf_base64 and self.pdf_base64.strip()):
            raise ValueError("Campo 'pdf_base64' e obrigatorio quando tipo_fonte='pdf'.")
        return self


class ChatRefeicaoAnexoInput(BaseModel):
    tipo_fonte: Literal["imagem", "audio"]
    imagem_url: str | None = None
    audio_base64: str | None = None
    nome_arquivo: str | None = None
    inferir_quando_ausente: bool = True

    @model_validator(mode="after")
    def _validate_payload(self) -> "ChatRefeicaoAnexoInput":
        if self.tipo_fonte == "imagem" and not (self.imagem_url and self.imagem_url.strip()):
            raise ValueError("Campo 'imagem_url' e obrigatorio quando tipo_fonte='imagem'.")
        if self.tipo_fonte == "audio" and not (self.audio_base64 and self.audio_base64.strip()):
            raise ValueError("Campo 'audio_base64' e obrigatorio quando tipo_fonte='audio'.")
        return self


class OpenAIChatRequest(BaseModel):
    prompt: str = Field(min_length=1, description="Prompt enviado para a OpenAI")
    conversation_id: str | None = Field(
        default=None,
        description="Identificador da conversa para memoria de curto prazo.",
    )
    usar_memoria: bool = Field(
        default=True,
        description="Quando true, aplica memoria controlada na conversa.",
    )
    metadados_conversa: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados opcionais da conversa (ex.: user_id, canal).",
    )
    plano_anexo: ChatPlanoAnexoInput | None = Field(
        default=None,
        description="Anexo opcional de plano alimentar para processamento via pipeline (imagem ou pdf).",
    )
    refeicao_anexo: ChatRefeicaoAnexoInput | None = Field(
        default=None,
        description="Anexo opcional para registro de refeicao por foto (imagem) ou audio.",
    )


class ChatRoteamento(BaseModel):
    pipeline: ChatPipelineNome
    handler: str
    status: Literal["sucesso", "parcial", "erro"] = "sucesso"
    warnings: list[str] = Field(default_factory=list)
    precisa_revisao: bool = False
    metadados: dict[str, Any] = Field(default_factory=dict)


class ChatMemoriaEstado(BaseModel):
    conversation_id: str
    total_turnos: int = Field(ge=0)
    turnos_curto_prazo: int = Field(ge=0)
    turnos_resumidos: int = Field(ge=0)
    resumo_presente: bool = False
    contexto_chars: int = Field(ge=0)
    limite_aplicado: bool = False
    ultima_intencao: IntencaoChatNome | None = None
    ultimo_pipeline: ChatPipelineNome | None = None
    metadados: dict[str, str] = Field(default_factory=dict)
    atualizada_em: datetime


class OpenAIChatResponse(BaseModel):
    model: str
    response: str
    intencao_detectada: IntencaoChatDetectada | None = None
    roteamento: ChatRoteamento | None = None
    conversation_id: str | None = None
    memoria: ChatMemoriaEstado | None = None
