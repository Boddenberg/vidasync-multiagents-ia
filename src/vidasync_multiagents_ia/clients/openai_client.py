import io
import json
import logging
from time import perf_counter
from typing import Any

from openai import OpenAI

from vidasync_multiagents_ia.observability import record_external_request, record_external_timeout


class OpenAIClient:
    def __init__(self, api_key: str, timeout_seconds: float = 60.0) -> None:
        self._client = OpenAI(api_key=api_key.strip(), timeout=timeout_seconds)
        self._logger = logging.getLogger(__name__)

    def generate_text(self, *, model: str, prompt: str) -> str:
        operation = "generate_text"
        started = perf_counter()
        self._logger.info(
            "openai.request",
            extra={"client": "openai", "operation": operation, "model": model, "prompt_chars": len(prompt)},
        )
        try:
            response = self._client.responses.create(model=model, input=prompt)
            output = response.output_text or ""
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.info(
                "openai.response",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": "ok",
                    "duration_ms": round(duration_ms, 4),
                    "output_chars": len(output),
                },
            )
            record_external_request(client="openai", operation=operation, status="ok", duration_ms=duration_ms)
            return output
        except Exception:
            duration_ms = (perf_counter() - started) * 1000.0
            status = _resolve_error_status()
            self._logger.exception(
                "openai.error",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": status,
                    "timeout": status == "timeout",
                    "duration_ms": round(duration_ms, 4),
                },
            )
            record_external_request(client="openai", operation=operation, status=status, duration_ms=duration_ms)
            if status == "timeout":
                record_external_timeout(client="openai", operation=operation)
            raise

    def generate_json_from_image(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_url: str,
    ) -> dict[str, Any]:
        operation = "generate_json_from_image"
        started = perf_counter()
        self._logger.info(
            "openai.request",
            extra={
                "client": "openai",
                "operation": operation,
                "model": model,
                "system_prompt_chars": len(system_prompt),
                "user_prompt_chars": len(user_prompt),
                "image_url": image_url,
            },
        )
        try:
            response = self._client.responses.create(
                model=model,
                temperature=0,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_prompt},
                            {"type": "input_image", "image_url": image_url},
                        ],
                    },
                ],
            )
            output_text = response.output_text or ""
            parsed = _extract_json_object(output_text)
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.info(
                "openai.response",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": "ok",
                    "duration_ms": round(duration_ms, 4),
                    "output_chars": len(output_text),
                },
            )
            record_external_request(client="openai", operation=operation, status="ok", duration_ms=duration_ms)
            return parsed
        except Exception:
            duration_ms = (perf_counter() - started) * 1000.0
            status = _resolve_error_status()
            self._logger.exception(
                "openai.error",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": status,
                    "timeout": status == "timeout",
                    "duration_ms": round(duration_ms, 4),
                },
            )
            record_external_request(client="openai", operation=operation, status=status, duration_ms=duration_ms)
            if status == "timeout":
                record_external_timeout(client="openai", operation=operation)
            raise

    def extract_text_from_image(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_url: str,
    ) -> str:
        operation = "extract_text_from_image"
        started = perf_counter()
        self._logger.info(
            "openai.request",
            extra={
                "client": "openai",
                "operation": operation,
                "model": model,
                "system_prompt_chars": len(system_prompt),
                "user_prompt_chars": len(user_prompt),
                "image_url": image_url,
            },
        )
        try:
            response = self._client.responses.create(
                model=model,
                temperature=0,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_prompt},
                            {"type": "input_image", "image_url": image_url},
                        ],
                    },
                ],
            )
            output = (response.output_text or "").strip()
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.info(
                "openai.response",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": "ok",
                    "duration_ms": round(duration_ms, 4),
                    "output_chars": len(output),
                },
            )
            record_external_request(client="openai", operation=operation, status="ok", duration_ms=duration_ms)
            return output
        except Exception:
            duration_ms = (perf_counter() - started) * 1000.0
            status = _resolve_error_status()
            self._logger.exception(
                "openai.error",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": status,
                    "timeout": status == "timeout",
                    "duration_ms": round(duration_ms, 4),
                },
            )
            record_external_request(client="openai", operation=operation, status=status, duration_ms=duration_ms)
            if status == "timeout":
                record_external_timeout(client="openai", operation=operation)
            raise

    def extract_text_from_pdf(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        pdf_bytes: bytes,
        filename: str,
    ) -> str:
        operation = "extract_text_from_pdf"
        started = perf_counter()
        self._logger.info(
            "openai.request",
            extra={
                "client": "openai",
                "operation": operation,
                "model": model,
                "system_prompt_chars": len(system_prompt),
                "user_prompt_chars": len(user_prompt),
                "file_name": filename,
                "pdf_bytes": len(pdf_bytes),
            },
        )

        file_id: str | None = None
        try:
            # /**** Upload temporario do PDF para uso no Responses API. ****/
            pdf_buffer = io.BytesIO(pdf_bytes)
            pdf_buffer.name = filename
            uploaded = self._client.files.create(
                file=(filename, pdf_buffer, "application/pdf"),
                purpose="user_data",
            )
            file_id = uploaded.id

            response = self._client.responses.create(
                model=model,
                temperature=0,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_prompt},
                            {"type": "input_file", "file_id": file_id},
                        ],
                    },
                ],
            )
            output = (response.output_text or "").strip()
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.info(
                "openai.response",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": "ok",
                    "duration_ms": round(duration_ms, 4),
                    "output_chars": len(output),
                },
            )
            record_external_request(client="openai", operation=operation, status="ok", duration_ms=duration_ms)
            return output
        except Exception:
            duration_ms = (perf_counter() - started) * 1000.0
            status = _resolve_error_status()
            self._logger.exception(
                "openai.error",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": status,
                    "timeout": status == "timeout",
                    "duration_ms": round(duration_ms, 4),
                },
            )
            record_external_request(client="openai", operation=operation, status=status, duration_ms=duration_ms)
            if status == "timeout":
                record_external_timeout(client="openai", operation=operation)
            raise
        finally:
            if file_id:
                # /**** Limpeza best-effort do arquivo temporario no provedor. ****/
                try:
                    self._client.files.delete(file_id)
                except Exception:
                    self._logger.warning(
                        "openai.file_cleanup.failed",
                        extra={
                            "client": "openai",
                            "operation": operation,
                            "file_id": file_id,
                        },
                    )

    def generate_json_from_pdf(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        pdf_bytes: bytes,
        filename: str,
    ) -> dict[str, Any]:
        operation = "generate_json_from_pdf"
        started = perf_counter()
        self._logger.info(
            "openai.request",
            extra={
                "client": "openai",
                "operation": operation,
                "model": model,
                "system_prompt_chars": len(system_prompt),
                "user_prompt_chars": len(user_prompt),
                "file_name": filename,
                "pdf_bytes": len(pdf_bytes),
            },
        )

        file_id: str | None = None
        try:
            # /**** Upload temporario do PDF para uso no Responses API. ****/
            pdf_buffer = io.BytesIO(pdf_bytes)
            pdf_buffer.name = filename
            uploaded = self._client.files.create(
                file=(filename, pdf_buffer, "application/pdf"),
                purpose="user_data",
            )
            file_id = uploaded.id

            response = self._client.responses.create(
                model=model,
                temperature=0,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_prompt},
                            {"type": "input_file", "file_id": file_id},
                        ],
                    },
                ],
            )
            output_text = response.output_text or ""
            parsed = _extract_json_object(output_text)
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.info(
                "openai.response",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": "ok",
                    "duration_ms": round(duration_ms, 4),
                    "output_chars": len(output_text),
                },
            )
            record_external_request(client="openai", operation=operation, status="ok", duration_ms=duration_ms)
            return parsed
        except Exception:
            duration_ms = (perf_counter() - started) * 1000.0
            status = _resolve_error_status()
            self._logger.exception(
                "openai.error",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": status,
                    "timeout": status == "timeout",
                    "duration_ms": round(duration_ms, 4),
                },
            )
            record_external_request(client="openai", operation=operation, status=status, duration_ms=duration_ms)
            if status == "timeout":
                record_external_timeout(client="openai", operation=operation)
            raise
        finally:
            if file_id:
                try:
                    self._client.files.delete(file_id)
                except Exception:
                    self._logger.warning(
                        "openai.file_cleanup.failed",
                        extra={
                            "client": "openai",
                            "operation": operation,
                            "file_id": file_id,
                        },
                    )

    def generate_json_from_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        operation = "generate_json_from_text"
        started = perf_counter()
        self._logger.info(
            "openai.request",
            extra={
                "client": "openai",
                "operation": operation,
                "model": model,
                "system_prompt_chars": len(system_prompt),
                "user_prompt_chars": len(user_prompt),
            },
        )
        try:
            response = self._client.responses.create(
                model=model,
                temperature=0,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_prompt}],
                    },
                ],
            )
            output_text = response.output_text or ""
            parsed = _extract_json_object(output_text)
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.info(
                "openai.response",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": "ok",
                    "duration_ms": round(duration_ms, 4),
                    "output_chars": len(output_text),
                },
            )
            record_external_request(client="openai", operation=operation, status="ok", duration_ms=duration_ms)
            return parsed
        except Exception:
            duration_ms = (perf_counter() - started) * 1000.0
            status = _resolve_error_status()
            self._logger.exception(
                "openai.error",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": status,
                    "timeout": status == "timeout",
                    "duration_ms": round(duration_ms, 4),
                },
            )
            record_external_request(client="openai", operation=operation, status=status, duration_ms=duration_ms)
            if status == "timeout":
                record_external_timeout(client="openai", operation=operation)
            raise

    def transcribe_audio(
        self,
        *,
        model: str,
        audio_bytes: bytes,
        filename: str,
        language: str | None = None,
    ) -> str:
        operation = "transcribe_audio"
        started = perf_counter()
        self._logger.info(
            "openai.request",
            extra={
                "client": "openai",
                "operation": operation,
                "model": model,
                "file_name": filename,
                "audio_bytes": len(audio_bytes),
                "language": language,
            },
        )
        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.name = filename

        try:
            response = self._client.audio.transcriptions.create(
                model=model,
                file=audio_buffer,
                language=language,
            )
            output = (getattr(response, "text", None) or "").strip()
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.info(
                "openai.response",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": "ok",
                    "duration_ms": round(duration_ms, 4),
                    "output_chars": len(output),
                },
            )
            record_external_request(client="openai", operation=operation, status="ok", duration_ms=duration_ms)
            return output
        except Exception:
            duration_ms = (perf_counter() - started) * 1000.0
            status = _resolve_error_status()
            self._logger.exception(
                "openai.error",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "status": status,
                    "timeout": status == "timeout",
                    "duration_ms": round(duration_ms, 4),
                },
            )
            record_external_request(client="openai", operation=operation, status=status, duration_ms=duration_ms)
            if status == "timeout":
                record_external_timeout(client="openai", operation=operation)
            raise


def _extract_json_object(output_text: str) -> dict[str, Any]:
    raw = output_text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError("Resposta da OpenAI nao retornou JSON valido.")


def _resolve_error_status() -> str:
    # /**** Mantem timeout separado de erro generico para metricas de troubleshooting. ****/
    import sys

    exc = sys.exc_info()[1]
    current = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if "timeout" in name or "timed out" in message or "timeout" in message:
            return "timeout"
        current = current.__cause__ or current.__context__
    return "error"
