from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_ai_router_service
from vidasync_multiagents_ia.schemas import AIRouterRequest, AIRouterResponse
from vidasync_multiagents_ia.services import AIRouterService

router = APIRouter(prefix="/ai", tags=["ai-interno"])


@router.post("/router", response_model=AIRouterResponse)
def route_ai_context(
    payload: AIRouterRequest,
    service: AIRouterService = Depends(get_ai_router_service),
) -> AIRouterResponse:
    # /**** Gateway interno para roteamento por contexto na camada de agentes. ****/
    return service.route(payload)

