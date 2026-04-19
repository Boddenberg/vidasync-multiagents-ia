from dataclasses import dataclass
from typing import Protocol

from vidasync_multiagents_ia.schemas import PlanoPipelineE2ETesteResponse


@dataclass(slots=True)
class PlanoPipelineExecutionInput:
    tipo_fonte: str
    contexto: str
    idioma: str
    executar_ocr_literal: bool
    imagem_url: str | None = None
    pdf_bytes: bytes | None = None
    nome_arquivo: str | None = None


class AiOrchestrator(Protocol):
    # Interface estavel para trocar engine de orquestracao sem quebrar API.
    def execute_plano_pipeline(self, *, request: PlanoPipelineExecutionInput) -> PlanoPipelineE2ETesteResponse:
        ...
