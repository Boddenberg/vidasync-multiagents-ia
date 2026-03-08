from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_foto_alimentos_service
from vidasync_multiagents_ia.schemas import (
    EstimativaPorcoesFotoRequest,
    EstimativaPorcoesFotoResponse,
    IdentificacaoFotoRequest,
    IdentificacaoFotoResponse,
)
from vidasync_multiagents_ia.services import FotoAlimentosService

router = APIRouter(prefix="/agentes/fotos", tags=["agentes-fotos"])


@router.post("/identificar-comida", response_model=IdentificacaoFotoResponse)
def identificar_se_e_comida(
    payload: IdentificacaoFotoRequest,
    service: FotoAlimentosService = Depends(get_foto_alimentos_service),
) -> IdentificacaoFotoResponse:
    return service.identificar_se_e_foto_de_comida(
        imagem_url=payload.imagem_url,
        contexto=payload.contexto,
        idioma=payload.idioma,
    )


@router.post("/estimar-porcoes", response_model=EstimativaPorcoesFotoResponse)
def estimar_porcoes(
    payload: EstimativaPorcoesFotoRequest,
    service: FotoAlimentosService = Depends(get_foto_alimentos_service),
) -> EstimativaPorcoesFotoResponse:
    return service.estimar_porcoes_do_prato(
        imagem_url=payload.imagem_url,
        contexto=payload.contexto,
        idioma=payload.idioma,
    )
