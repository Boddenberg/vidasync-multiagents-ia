from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_tbca_service
from vidasync_multiagents_ia.schemas import TBCASearchRequest, TBCASearchResponse
from vidasync_multiagents_ia.services import TBCAService

router = APIRouter(prefix="/tbca", tags=["tbca"])


@router.post("/search", response_model=TBCASearchResponse)
def search_tbca_food(
    payload: TBCASearchRequest,
    service: TBCAService = Depends(get_tbca_service),
) -> TBCASearchResponse:
    return service.search(query=payload.consulta, grams=payload.gramas)
