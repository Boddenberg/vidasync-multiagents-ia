from vidasync_multiagents_ia.clients.openai_client import _detect_image_format


def test_detect_image_format_identifica_png_por_assinatura() -> None:
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    assert _detect_image_format(image_bytes=image_bytes, content_type="image/png") == "png"


def test_detect_image_format_identifica_webp_por_assinatura() -> None:
    image_bytes = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8
    assert _detect_image_format(image_bytes=image_bytes, content_type="image/webp") == "webp"


def test_detect_image_format_identifica_avif_quando_mime_esta_incorreto() -> None:
    # /**** Caso real: arquivo AVIF salvo como .png e entregue com content-type image/png. ****/
    image_bytes = b"\x00\x00\x00 ftypavif" + b"\x00" * 32
    assert _detect_image_format(image_bytes=image_bytes, content_type="image/png") == "avif"
