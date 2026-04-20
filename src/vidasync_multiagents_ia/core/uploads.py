"""Shared helpers to validate and read FastAPI UploadFile payloads safely."""
from __future__ import annotations

from typing import Iterable, Protocol

from vidasync_multiagents_ia.core.errors import ServiceError


class _UploadFileLike(Protocol):
    content_type: str | None
    filename: str | None

    async def read(self, size: int = -1) -> bytes:
        ...


_DEFAULT_CHUNK_BYTES = 1024 * 1024


def validate_upload_content_type(
    upload: _UploadFileLike,
    *,
    allowed_content_types: Iterable[str],
    allowed_extensions: Iterable[str] | None = None,
    label: str = "arquivo",
) -> None:
    """Reject uploads whose declared content-type or extension is outside the allowlist.

    - `allowed_content_types` is matched as substring against the declared header
      (case-insensitive) so entries like "pdf" match "application/pdf".
    - When the client omits the header we fall back to the filename extension.
    - Empty filename is rejected only when `allowed_extensions` is provided.
    """
    content_type = (upload.content_type or "").strip().lower()
    filename = (upload.filename or "").strip().lower()
    allow_ct = tuple(token.lower() for token in allowed_content_types if token)

    if content_type:
        if not any(token in content_type for token in allow_ct):
            raise ServiceError(
                f"{label.capitalize()} invalido: content-type '{content_type}' fora da lista permitida.",
                status_code=415,
            )

    if allowed_extensions is None:
        return

    allow_ext = tuple(ext.lower().lstrip(".") for ext in allowed_extensions if ext)
    if not filename:
        raise ServiceError(
            f"{label.capitalize()} invalido: nome de arquivo ausente.",
            status_code=400,
        )
    if not any(filename.endswith(f".{ext}") for ext in allow_ext):
        raise ServiceError(
            f"{label.capitalize()} invalido: extensao nao permitida ({filename}).",
            status_code=400,
        )


async def read_upload_with_limit(
    upload: _UploadFileLike,
    *,
    max_bytes: int,
    label: str = "arquivo",
    chunk_bytes: int = _DEFAULT_CHUNK_BYTES,
) -> bytes:
    """Stream an UploadFile into memory with a hard ceiling, raising 413 on overflow."""
    collected = bytearray()
    while True:
        chunk = await upload.read(chunk_bytes)
        if not chunk:
            break
        collected.extend(chunk)
        if len(collected) > max_bytes:
            raise ServiceError(
                f"{label.capitalize()} acima do limite de {max_bytes} bytes.",
                status_code=413,
            )
    return bytes(collected)
