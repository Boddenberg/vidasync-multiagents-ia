from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import ChatJudgeTelemetryResponse
from vidasync_multiagents_ia.services.chat_judge_supabase_repository import (
    ChatJudgeSupabaseRepository,
)
from vidasync_multiagents_ia.services.chat_judge_tracking_mapper import (
    map_chat_judge_tracking_record_to_telemetry_response,
)


class ChatJudgeTrackingService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: ChatJudgeSupabaseRepository | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository or ChatJudgeSupabaseRepository(settings=settings)

    def fetch_by_evaluation_id(self, evaluation_id: str) -> ChatJudgeTelemetryResponse:
        normalized_evaluation_id = str(evaluation_id).strip()
        if not normalized_evaluation_id:
            raise ServiceError("evaluation_id do chat judge e obrigatorio.", status_code=400)

        record = self._repository.fetch_by_evaluation_id(normalized_evaluation_id)
        if record is None:
            raise ServiceError("Avaliacao do chat judge nao encontrada.", status_code=404)

        return map_chat_judge_tracking_record_to_telemetry_response(record)
