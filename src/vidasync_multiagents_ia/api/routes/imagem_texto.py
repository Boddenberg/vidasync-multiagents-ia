from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_imagem_texto_service
from vidasync_multiagents_ia.schemas import ImagemTextoRequest, ImagemTextoResponse
from vidasync_multiagents_ia.services import ImagemTextoService

router = APIRouter(prefix="/agentes/imagens", tags=["agentes-imagens"])


@router.post("/transcrever-texto", response_model=ImagemTextoResponse)
def transcrever_texto_imagem(
    payload: ImagemTextoRequest,
    service: ImagemTextoService = Depends(get_imagem_texto_service),
) -> ImagemTextoResponse:
    return service.transcrever_textos_de_imagens(
        imagem_urls=payload.imagem_urls,
        contexto=payload.contexto,
        idioma=payload.idioma,
    )
