from time import perf_counter

from fastapi import APIRouter, BackgroundTasks, Depends

from vidasync_multiagents_ia.api.dependencies import (
    get_chat_judge_async_service,
    get_chat_judge_service,
    get_chat_judge_tracking_service,
    get_openai_chat_service,
)
from vidasync_multiagents_ia.schemas import (
    ChatJudgeEvaluationInput,
    ChatJudgeResult,
    ChatJudgeTelemetryResponse,
    OpenAIChatRequest,
    OpenAIChatResponse,
)
from vidasync_multiagents_ia.services import (
    ChatJudgeAsyncService,
    ChatJudgeService,
    ChatJudgeTrackingService,
    OpenAIChatService,
)

router = APIRouter(prefix="/v1/openai", tags=["openai"])


@router.post("/chat", response_model=OpenAIChatResponse)
def openai_chat(
    payload: OpenAIChatRequest,
    background_tasks: BackgroundTasks,
    service: OpenAIChatService = Depends(get_openai_chat_service),
    judge_async_service: ChatJudgeAsyncService = Depends(get_chat_judge_async_service),
) -> OpenAIChatResponse:
    plano_anexo = (
        payload.plano_anexo.model_dump(exclude_none=True, exclude_defaults=True)
        if payload.plano_anexo
        else None
    )
    refeicao_anexo = (
        payload.refeicao_anexo.model_dump(exclude_none=True, exclude_defaults=True)
        if payload.refeicao_anexo
        else None
    )
    started = perf_counter()
    response = service.chat(
        payload.prompt,
        conversation_id=payload.conversation_id,
        usar_memoria=payload.usar_memoria,
        metadados_conversa={str(key): str(value) for key, value in payload.metadados_conversa.items()},
        plano_anexo=plano_anexo,
        refeicao_anexo=refeicao_anexo,
    )
    duration_ms = (perf_counter() - started) * 1000.0
    prepared_judge_evaluation = judge_async_service.prepare_chat_response_evaluation(
        prompt=payload.prompt,
        response=response,
        conversation_id=payload.conversation_id,
        usar_memoria=payload.usar_memoria,
        metadados_conversa=payload.metadados_conversa,
        plano_anexo_presente=payload.plano_anexo is not None,
        refeicao_anexo_presente=payload.refeicao_anexo is not None,
        source_duration_ms=round(duration_ms, 4),
    )
    if prepared_judge_evaluation is not None:
        background_tasks.add_task(
            judge_async_service.execute_prepared_chat_response_evaluation,
            prepared_judge_evaluation,
        )

    return response.model_copy(
        update={
            "judge": prepared_judge_evaluation.execution if prepared_judge_evaluation else None,
        }
    )


@router.post("/chat/judge", response_model=ChatJudgeResult)
def judge_openai_chat(
    payload: ChatJudgeEvaluationInput,
    service: ChatJudgeService = Depends(get_chat_judge_service),
) -> ChatJudgeResult:
    return service.evaluate(payload)


@router.get("/chat/judge/{evaluation_id}", response_model=ChatJudgeTelemetryResponse)
def get_openai_chat_judge_tracking(
    evaluation_id: str,
    service: ChatJudgeTrackingService = Depends(get_chat_judge_tracking_service),
) -> ChatJudgeTelemetryResponse:
    return service.fetch_by_evaluation_id(evaluation_id)
