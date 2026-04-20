import pytest

from vidasync_multiagents_ia.core import (
    ServiceError,
    read_upload_with_limit,
    validate_upload_content_type,
)


class _FakeUpload:
    def __init__(self, *, content_type: str | None, filename: str | None, data: bytes = b"") -> None:
        self.content_type = content_type
        self.filename = filename
        self._buffer = memoryview(data)
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if self._pos >= len(self._buffer):
            return b""
        end = len(self._buffer) if size < 0 else min(self._pos + size, len(self._buffer))
        chunk = bytes(self._buffer[self._pos : end])
        self._pos = end
        return chunk


def test_validate_content_type_rejects_unallowed_header() -> None:
    upload = _FakeUpload(content_type="image/png", filename="a.pdf")
    with pytest.raises(ServiceError) as exc:
        validate_upload_content_type(
            upload,
            allowed_content_types=("pdf",),
            label="arquivo PDF",
        )
    assert exc.value.status_code == 415


def test_validate_content_type_accepts_substring_match() -> None:
    upload = _FakeUpload(content_type="application/pdf", filename="ok.pdf")
    validate_upload_content_type(
        upload,
        allowed_content_types=("pdf",),
        allowed_extensions=("pdf",),
        label="arquivo PDF",
    )


def test_validate_content_type_enforces_extension_when_header_missing() -> None:
    upload = _FakeUpload(content_type=None, filename="sem_extensao")
    with pytest.raises(ServiceError) as exc:
        validate_upload_content_type(
            upload,
            allowed_content_types=("pdf",),
            allowed_extensions=("pdf",),
        )
    assert exc.value.status_code == 400


def test_validate_content_type_rejects_missing_filename_when_extensions_required() -> None:
    upload = _FakeUpload(content_type=None, filename=None)
    with pytest.raises(ServiceError):
        validate_upload_content_type(
            upload,
            allowed_content_types=("pdf",),
            allowed_extensions=("pdf",),
        )


def test_validate_content_type_skips_extension_when_none_requested() -> None:
    upload = _FakeUpload(content_type="audio/webm", filename="")
    validate_upload_content_type(upload, allowed_content_types=("audio/",))


def test_read_upload_with_limit_returns_all_bytes_when_below_max() -> None:
    import asyncio

    upload = _FakeUpload(content_type=None, filename=None, data=b"hello world")
    result = asyncio.run(read_upload_with_limit(upload, max_bytes=1024))
    assert result == b"hello world"


def test_read_upload_with_limit_raises_413_above_max() -> None:
    import asyncio

    upload = _FakeUpload(content_type=None, filename=None, data=b"x" * 2048)
    with pytest.raises(ServiceError) as exc:
        asyncio.run(read_upload_with_limit(upload, max_bytes=128))
    assert exc.value.status_code == 413
