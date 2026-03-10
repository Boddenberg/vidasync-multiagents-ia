import base64

from vidasync_multiagents_ia.clients import openai_client


def test_build_image_data_url_fallback_converte_avif_para_jpeg(monkeypatch) -> None:
    avif_bytes = b"\x00\x00\x00 ftypavif" + b"\x00" * 48
    jpeg_bytes = b"\xff\xd8\xff" + b"\x00" * 24

    monkeypatch.setattr(
        openai_client,
        "_download_image_bytes",
        lambda _image_url: (avif_bytes, "image/png"),
    )
    monkeypatch.setattr(
        openai_client,
        "_convert_unsupported_image_for_openai",
        lambda *, image_bytes, detected_format: (jpeg_bytes, "jpeg"),
    )

    data_url, detected_format, content_type, image_bytes = openai_client._build_image_data_url_fallback(
        "https://example.com/imagem.png"
    )

    expected_data_url = f"data:image/jpeg;base64,{base64.b64encode(jpeg_bytes).decode('ascii')}"
    assert data_url == expected_data_url
    assert detected_format == "jpeg"
    assert content_type == "image/png"
    assert image_bytes == len(jpeg_bytes)


def test_build_image_data_url_fallback_retorna_none_quando_avif_sem_conversao(monkeypatch) -> None:
    avif_bytes = b"\x00\x00\x00 ftypavif" + b"\x00" * 48

    monkeypatch.setattr(
        openai_client,
        "_download_image_bytes",
        lambda _image_url: (avif_bytes, "image/png"),
    )
    monkeypatch.setattr(
        openai_client,
        "_convert_unsupported_image_for_openai",
        lambda *, image_bytes, detected_format: None,
    )

    data_url, detected_format, content_type, image_bytes = openai_client._build_image_data_url_fallback(
        "https://example.com/imagem.png"
    )

    assert data_url is None
    assert detected_format == "avif"
    assert content_type == "image/png"
    assert image_bytes == len(avif_bytes)


def test_build_image_data_url_fallback_passa_direto_quando_png_valido(monkeypatch) -> None:
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    convert_called = False

    def _fake_convert_unsupported_image_for_openai(*, image_bytes: bytes, detected_format: str | None):
        nonlocal convert_called
        convert_called = True
        return b"", "jpeg"

    monkeypatch.setattr(
        openai_client,
        "_download_image_bytes",
        lambda _image_url: (png_bytes, "image/png"),
    )
    monkeypatch.setattr(
        openai_client,
        "_convert_unsupported_image_for_openai",
        _fake_convert_unsupported_image_for_openai,
    )

    data_url, detected_format, content_type, image_bytes = openai_client._build_image_data_url_fallback(
        "https://example.com/imagem.png"
    )

    expected_data_url = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"
    assert data_url == expected_data_url
    assert detected_format == "png"
    assert content_type == "image/png"
    assert image_bytes == len(png_bytes)
    assert convert_called is False
