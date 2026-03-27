import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability.payload_preview import preview_json, sanitize_url
from vidasync_multiagents_ia.schemas import ChatJudgeTrackingRecord


class ChatJudgeSupabaseRepository:
    def __init__(
        self,
        *,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._logger = logging.getLogger(__name__)

    @property
    def enabled(self) -> bool:
        return bool(
            self._settings.supabase_url.strip()
            and self._settings.supabase_service_role_key.strip()
            and self._settings.chat_judge_supabase_table.strip()
        )

    def upsert(self, record: ChatJudgeTrackingRecord) -> ChatJudgeTrackingRecord:
        if not self.enabled:
            raise ServiceError(
                "Persistencia do chat judge no Supabase nao esta configurada.",
                status_code=500,
            )

        endpoint = self._build_endpoint()
        payload = [record.model_dump(mode="json", exclude_none=False)]
        encoded_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self._logger.info(
            "💾 Chat judge Supabase upsert started.",
            extra={
                "judge_event": "chat_judge_supabase_repository.upsert_started",
                "storage": {
                    "backend": "supabase",
                    "table": self._settings.chat_judge_supabase_table,
                    "endpoint": sanitize_url(endpoint),
                },
                "identifiers": {
                    "evaluation_id": record.evaluation_id,
                    "request_id": record.request_id,
                    "conversation_id": record.conversation_id,
                    "message_id": record.message_id,
                },
                "judge_status": record.judge_status,
                "payload_preview": preview_json(payload, max_chars=self._settings.log_internal_max_body_chars),
            },
        )

        request = Request(
            endpoint,
            data=encoded_payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "apikey": self._settings.supabase_service_role_key,
                "Authorization": f"Bearer {self._settings.supabase_service_role_key}",
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._settings.chat_judge_supabase_timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            response_body = _read_http_error_body(exc)
            self._logger.exception(
                "❌ Chat judge Supabase upsert failed.",
                extra={
                    "judge_event": "chat_judge_supabase_repository.upsert_failed",
                    "storage": {
                        "backend": "supabase",
                        "table": self._settings.chat_judge_supabase_table,
                        "endpoint": sanitize_url(endpoint),
                    },
                    "identifiers": {
                        "evaluation_id": record.evaluation_id,
                        "request_id": record.request_id,
                        "conversation_id": record.conversation_id,
                        "message_id": record.message_id,
                    },
                    "http_status": getattr(exc, "code", None),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "response_body_preview": _preview_json_text(
                        response_body,
                        max_chars=self._settings.log_internal_max_body_chars,
                    ),
                },
            )
            raise ServiceError("Falha ao persistir chat judge no Supabase.", status_code=500) from exc
        except URLError as exc:
            self._logger.exception(
                "❌ Chat judge Supabase request failed.",
                extra={
                    "judge_event": "chat_judge_supabase_repository.request_failed",
                    "storage": {
                        "backend": "supabase",
                        "table": self._settings.chat_judge_supabase_table,
                        "endpoint": sanitize_url(endpoint),
                    },
                    "identifiers": {
                        "evaluation_id": record.evaluation_id,
                        "request_id": record.request_id,
                        "conversation_id": record.conversation_id,
                        "message_id": record.message_id,
                    },
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise ServiceError("Falha de conectividade ao persistir chat judge no Supabase.", status_code=500) from exc

        parsed_row = _parse_upsert_response(raw_body)
        stored_record = ChatJudgeTrackingRecord.model_validate(parsed_row)
        self._logger.info(
            "👍 Chat judge Supabase upsert completed.",
            extra={
                "judge_event": "chat_judge_supabase_repository.upsert_completed",
                "storage": {
                    "backend": "supabase",
                    "table": self._settings.chat_judge_supabase_table,
                },
                "identifiers": {
                    "evaluation_id": stored_record.evaluation_id,
                    "request_id": stored_record.request_id,
                    "conversation_id": stored_record.conversation_id,
                    "message_id": stored_record.message_id,
                },
                "judge_status": stored_record.judge_status,
                "response_body_preview": preview_json(
                    parsed_row,
                    max_chars=self._settings.log_internal_max_body_chars,
                ),
            },
        )
        return stored_record

    def fetch_by_evaluation_id(self, evaluation_id: str) -> ChatJudgeTrackingRecord | None:
        if not self.enabled:
            raise ServiceError(
                "Persistencia do chat judge no Supabase nao esta configurada.",
                status_code=500,
            )

        normalized_evaluation_id = str(evaluation_id).strip()
        if not normalized_evaluation_id:
            raise ServiceError("evaluation_id do chat judge e obrigatorio.", status_code=400)

        endpoint = self._build_select_endpoint(
            filters={
                "evaluation_id": f"eq.{quote(normalized_evaluation_id, safe='-_.~')}",
            }
        )
        request = Request(
            endpoint,
            headers={
                "Accept": "application/json",
                "apikey": self._settings.supabase_service_role_key,
                "Authorization": f"Bearer {self._settings.supabase_service_role_key}",
            },
            method="GET",
        )

        self._logger.info(
            "Chat judge Supabase fetch started.",
            extra={
                "judge_event": "chat_judge_supabase_repository.fetch_started",
                "storage": {
                    "backend": "supabase",
                    "table": self._settings.chat_judge_supabase_table,
                    "endpoint": sanitize_url(endpoint),
                },
                "identifiers": {"evaluation_id": normalized_evaluation_id},
            },
        )

        try:
            with urlopen(request, timeout=self._settings.chat_judge_supabase_timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            response_body = _read_http_error_body(exc)
            self._logger.exception(
                "Chat judge Supabase fetch failed.",
                extra={
                    "judge_event": "chat_judge_supabase_repository.fetch_failed",
                    "storage": {
                        "backend": "supabase",
                        "table": self._settings.chat_judge_supabase_table,
                        "endpoint": sanitize_url(endpoint),
                    },
                    "identifiers": {"evaluation_id": normalized_evaluation_id},
                    "http_status": getattr(exc, "code", None),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "response_body_preview": _preview_json_text(
                        response_body,
                        max_chars=self._settings.log_internal_max_body_chars,
                    ),
                },
            )
            raise ServiceError("Falha ao consultar chat judge no Supabase.", status_code=500) from exc
        except URLError as exc:
            self._logger.exception(
                "Chat judge Supabase fetch request failed.",
                extra={
                    "judge_event": "chat_judge_supabase_repository.fetch_request_failed",
                    "storage": {
                        "backend": "supabase",
                        "table": self._settings.chat_judge_supabase_table,
                        "endpoint": sanitize_url(endpoint),
                    },
                    "identifiers": {"evaluation_id": normalized_evaluation_id},
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise ServiceError("Falha de conectividade ao consultar chat judge no Supabase.", status_code=500) from exc

        rows = _parse_select_response(raw_body)
        if not rows:
            return None

        stored_record = ChatJudgeTrackingRecord.model_validate(rows[0])
        self._logger.info(
            "Chat judge Supabase fetch completed.",
            extra={
                "judge_event": "chat_judge_supabase_repository.fetch_completed",
                "storage": {
                    "backend": "supabase",
                    "table": self._settings.chat_judge_supabase_table,
                },
                "identifiers": {"evaluation_id": stored_record.evaluation_id},
                "judge_status": stored_record.judge_status,
            },
        )
        return stored_record

    def _build_endpoint(self) -> str:
        base_url = self._settings.supabase_url.strip().rstrip("/")
        table = quote(self._settings.chat_judge_supabase_table.strip(), safe="_")
        return f"{base_url}/rest/v1/{table}?on_conflict=evaluation_id"

    def _build_select_endpoint(self, *, filters: dict[str, str]) -> str:
        base_url = self._settings.supabase_url.strip().rstrip("/")
        table = quote(self._settings.chat_judge_supabase_table.strip(), safe="_")
        query = "&".join([*(f"{key}={value}" for key, value in filters.items()), "select=*"])
        return f"{base_url}/rest/v1/{table}?{query}"


def _parse_upsert_response(raw_body: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ServiceError("Supabase retornou JSON invalido ao persistir chat judge.", status_code=500) from exc

    if not isinstance(parsed, list) or not parsed:
        raise ServiceError("Supabase nao retornou o registro persistido do chat judge.", status_code=500)

    row = parsed[0]
    if not isinstance(row, dict):
        raise ServiceError("Supabase retornou um payload inesperado para o chat judge.", status_code=500)
    return row


def _parse_select_response(raw_body: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ServiceError("Supabase retornou JSON invalido ao consultar chat judge.", status_code=500) from exc

    if not isinstance(parsed, list):
        raise ServiceError("Supabase retornou um payload inesperado ao consultar chat judge.", status_code=500)

    rows: list[dict[str, Any]] = []
    for row in parsed:
        if not isinstance(row, dict):
            raise ServiceError("Supabase retornou um registro invalido do chat judge.", status_code=500)
        rows.append(row)
    return rows


def _read_http_error_body(error: HTTPError) -> str | None:
    try:
        return error.read().decode("utf-8")
    except Exception:
        return None


def _preview_json_text(raw_body: str | None, *, max_chars: int) -> Any | None:
    if not raw_body:
        return None
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body[:max_chars]
    return preview_json(parsed, max_chars=max_chars)
