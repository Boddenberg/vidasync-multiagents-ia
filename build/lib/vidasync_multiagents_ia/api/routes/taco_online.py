from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_taco_online_service
from vidasync_multiagents_ia.schemas import TacoOnlineFoodRequest, TacoOnlineFoodResponse
from vidasync_multiagents_ia.services import TacoOnlineService

router = APIRouter(prefix="/taco-online", tags=["taco-online"])


@router.post("/food", response_model=TacoOnlineFoodResponse)
def get_taco_online_food(
    payload: TacoOnlineFoodRequest,
    service: TacoOnlineService = Depends(get_taco_online_service),
) -> TacoOnlineFoodResponse:
    return service.get_food(
        slug=payload.slug,
        page_url=payload.url,
        query=payload.consulta,
        grams=payload.gramas,
    )
