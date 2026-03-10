import io
import json
import logging
import base64
import urllib.request
from time import perf_counter
from typing import Any

from openai import BadRequestError, OpenAI

from vidasync_multiagents_ia.observability import record_external_request, record_external_timeout
from vidasync_multiagents_ia.observability.payload_preview import preview_json, preview_text, sanitize_url

_SUPPORTED_IMAGE_FORMATS = {"jpeg", "png", "gif", "webp"}
_CONVERTIBLE_FALLBACK_IMAGE_FORMATS = {"avif"}
_MAX_FALLBACK_IMAGE_BYTES = 20 * 1024 * 1024


class OpenAIClient:
    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = 60.0,
        *,
        log_payloads: bool = True,
        log_max_chars: int = 4000,
    ) -> None:
        self._client = OpenAI(api_key=api_key.strip(), timeout=timeout_seconds)
        self._logger = logging.getLogger(__name__)
        self._log_payloads = log_payloads
        self._log_max_chars = max(256, log_max_chars)

    def generate_text(self, *, model: str, prompt: str) -> str:
        operation = "generate_text"
        started = perf_counter()
        self._logger.info(
            "openai.request",
            extra={
                "client": "openai",
                "operation": operation,
                "model": model,
                "prompt_chars": len(prompt),
                "prompt_preview": self._preview_text(prompt),
            },
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
                    "response_preview": self._preview_text(output),
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
                "system_prompt_preview": self._preview_text(system_prompt),
                "user_prompt_preview": self._preview_text(user_prompt),
                "image_url": sanitize_url(image_url),
            },
        )
        try:
            response = self._create_response_with_image(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_url=image_url,
                operation=operation,
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
                    "response_preview": self._preview_text(output_text),
                    "response_json_preview": self._preview_json(parsed),
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
                "system_prompt_preview": self._preview_text(system_prompt),
                "user_prompt_preview": self._preview_text(user_prompt),
                "image_url": sanitize_url(image_url),
            },
        )
        try:
            response = self._create_response_with_image(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_url=image_url,
                operation=operation,
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
                    "response_preview": self._preview_text(output),
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
                "system_prompt_preview": self._preview_text(system_prompt),
                "user_prompt_preview": self._preview_text(user_prompt),
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
                    "response_preview": self._preview_text(output),
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
                "system_prompt_preview": self._preview_text(system_prompt),
                "user_prompt_preview": self._preview_text(user_prompt),
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
                    "response_preview": self._preview_text(output_text),
                    "response_json_preview": self._preview_json(parsed),
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
                "system_prompt_preview": self._preview_text(system_prompt),
                "user_prompt_preview": self._preview_text(user_prompt),
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
                    "response_preview": self._preview_text(output_text),
                    "response_json_preview": self._preview_json(parsed),
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
                    "response_preview": self._preview_text(output),
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

    def _preview_text(self, value: str | bytes | None) -> str | None:
        if not self._log_payloads:
            return None
        return preview_text(value, max_chars=self._log_max_chars)

    def _preview_json(self, value: Any) -> str | None:
        if not self._log_payloads:
            return None
        return preview_json(value, max_chars=self._log_max_chars)

    def _create_response_with_image(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_url: str,
        operation: str,
    ) -> Any:
        request_input = _build_image_request_input(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image_ref=image_url,
        )
        try:
            return self._client.responses.create(
                model=model,
                temperature=0,
                input=request_input,
            )
        except BadRequestError as exc:
            if not _is_invalid_image_error(exc):
                raise

            fallback = _build_image_data_url_fallback(image_url)
            if fallback is None:
                raise

            data_url, detected_format, content_type, image_bytes = fallback
            if not data_url:
                self._logger.warning(
                    "openai.image.invalid_remote_payload",
                    extra={
                        "client": "openai",
                        "operation": operation,
                        "model": model,
                        "image_url": sanitize_url(image_url),
                        "detected_format": detected_format,
                        "content_type": content_type,
                        "image_bytes": image_bytes,
                    },
                )
                raise

            self._logger.warning(
                "openai.image.retry_data_url",
                extra={
                    "client": "openai",
                    "operation": operation,
                    "model": model,
                    "image_url": sanitize_url(image_url),
                    "fallback_format": detected_format,
                    "fallback_content_type": content_type,
                    "fallback_image_bytes": image_bytes,
                },
            )
            retry_input = _build_image_request_input(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_ref=data_url,
            )
            return self._client.responses.create(
                model=model,
                temperature=0,
                input=retry_input,
            )


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


def _build_image_request_input(*, system_prompt: str, user_prompt: str, image_ref: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": user_prompt},
                {"type": "input_image", "image_url": image_ref},
            ],
        },
    ]


def _is_invalid_image_error(exc: BadRequestError) -> bool:
    message = str(exc).lower()
    if "does not represent a valid image" in message:
        return True
    if "supported image formats" in message and "invalid" in message:
        return True
    return False


def _build_image_data_url_fallback(image_url: str) -> tuple[str | None, str | None, str | None, int] | None:
    try:
        image_bytes, content_type = _download_image_bytes(image_url)
    except Exception:
        return None

    if not image_bytes:
        return None, None, content_type, 0
    if len(image_bytes) > _MAX_FALLBACK_IMAGE_BYTES:
        return None, None, content_type, len(image_bytes)

    detected_format = _detect_image_format(image_bytes=image_bytes, content_type=content_type)
    if detected_format not in _SUPPORTED_IMAGE_FORMATS:
        converted = _convert_unsupported_image_for_openai(
            image_bytes=image_bytes,
            detected_format=detected_format,
        )
        if converted is None:
            return None, detected_format, content_type, len(image_bytes)
        image_bytes, detected_format = converted

    mime_type = _mime_type_from_image_format(detected_format)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"
    return data_url, detected_format, content_type, len(image_bytes)


def _convert_unsupported_image_for_openai(
    *,
    image_bytes: bytes,
    detected_format: str | None,
) -> tuple[bytes, str] | None:
    if detected_format not in _CONVERTIBLE_FALLBACK_IMAGE_FORMATS:
        return None

    try:
        from PIL import Image
    except Exception:
        return None

    # /**** Registro lazy do plugin para abrir AVIF quando disponivel. ****/
    if detected_format == "avif":
        try:
            __import__("pillow_avif")
        except Exception:
            return None

    try:
        with Image.open(io.BytesIO(image_bytes)) as source_image:
            converted_image = source_image.convert("RGBA")
            output_image = Image.new("RGB", converted_image.size, (255, 255, 255))
            output_image.paste(converted_image, mask=converted_image.getchannel("A"))
            output = io.BytesIO()
            output_image.save(output, format="JPEG", quality=92)
            return output.getvalue(), "jpeg"
    except Exception:
        return None


def _download_image_bytes(image_url: str) -> tuple[bytes, str | None]:
    request = urllib.request.Request(
        image_url,
        headers={"User-Agent": "vidasync-openai-client/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw_content_type = response.headers.get("Content-Type")
        return response.read(), raw_content_type


def _detect_image_format(*, image_bytes: bytes, content_type: str | None) -> str | None:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "gif"
    if len(image_bytes) >= 12 and image_bytes[0:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "webp"
    if len(image_bytes) >= 12 and image_bytes[4:8] == b"ftyp":
        major_brand = image_bytes[8:12].decode("ascii", errors="ignore").lower()
        if major_brand in {"avif", "avis"}:
            return "avif"
        if major_brand in {"heic", "heif", "heix", "hevc", "hevx", "mif1", "msf1"}:
            return "heic"

    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    content_type_map = {
        "image/png": "png",
        "image/jpeg": "jpeg",
        "image/jpg": "jpeg",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/avif": "avif",
        "image/heic": "heic",
        "image/heif": "heic",
    }
    return content_type_map.get(normalized_content_type)


def _mime_type_from_image_format(image_format: str) -> str:
    mime_by_format = {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }
    return mime_by_format[image_format]
