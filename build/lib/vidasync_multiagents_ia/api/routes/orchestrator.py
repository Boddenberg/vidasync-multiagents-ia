from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_orchestrator_service
from vidasync_multiagents_ia.schemas import OrchestrateRequest, OrchestrateResponse
from vidasync_multiagents_ia.services import OrchestratorService

router = APIRouter(tags=["orchestrator"])


@router.post("/orchestrate", response_model=OrchestrateResponse)
def orchestrate(
    payload: OrchestrateRequest,
    service: OrchestratorService = Depends(get_orchestrator_service),
) -> OrchestrateResponse:
    return OrchestrateResponse(result=service.orchestrate(payload.query))
