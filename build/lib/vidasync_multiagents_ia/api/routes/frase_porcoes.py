from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_frase_porcoes_service
from vidasync_multiagents_ia.schemas import FrasePorcoesRequest, FrasePorcoesResponse
from vidasync_multiagents_ia.services import FrasePorcoesService

router = APIRouter(prefix="/agentes/texto", tags=["agentes-texto"])


@router.post("/extrair-porcoes", response_model=FrasePorcoesResponse)
def extrair_porcoes_do_texto(
    payload: FrasePorcoesRequest,
    service: FrasePorcoesService = Depends(get_frase_porcoes_service),
) -> FrasePorcoesResponse:
    return service.extrair_porcoes(
        texto_transcrito=payload.texto_transcrito,
        contexto=payload.contexto,
        idioma=payload.idioma,
        inferir_quando_ausente=payload.inferir_quando_ausente,
    )
