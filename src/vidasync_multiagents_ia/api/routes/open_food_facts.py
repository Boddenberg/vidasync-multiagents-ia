from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_open_food_facts_service
from vidasync_multiagents_ia.schemas import OpenFoodFactsSearchRequest, OpenFoodFactsSearchResponse
from vidasync_multiagents_ia.services import OpenFoodFactsService

router = APIRouter(prefix="/open-food-facts", tags=["open-food-facts"])


@router.post("/search", response_model=OpenFoodFactsSearchResponse)
def search_open_food_facts(
    payload: OpenFoodFactsSearchRequest,
    service: OpenFoodFactsService = Depends(get_open_food_facts_service),
) -> OpenFoodFactsSearchResponse:
    return service.search(
        query=payload.consulta,
        grams=payload.gramas,
        page=payload.page,
        page_size=payload.page_size,
    )
