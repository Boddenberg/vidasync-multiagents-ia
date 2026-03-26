from vidasync_multiagents_ia.observability.payload_preview import preview_json, preview_text, sanitize_url


def test_sanitize_url_masks_sensitive_query_values() -> None:
    url = "https://example.com/img.jpg?token=abc123&x=1&api_key=secret"
    sanitized = sanitize_url(url)
    assert "token=***" in sanitized
    assert "api_key=***" in sanitized
    assert "x=1" in sanitized


def test_preview_text_truncates_and_masks_tokens() -> None:
    raw = '{"token":"abc123","value":"ok"}'
    preview = preview_text(raw, max_chars=20)
    assert preview is not None
    assert "***" in preview
    assert preview.endswith("...(truncated)")


def test_preview_json_mantem_estrutura_e_mascara_dados_sensiveis() -> None:
    preview = preview_json(
        {
            "token": "abc123",
            "items": [
                {"nome": "banana", "descricao": "x" * 50},
            ],
        },
        max_chars=20,
    )

    assert preview == {
        "token": "***",
        "items": [
            {"nome": "banana", "descricao": "xxxxxxxxxxxxxxxxxxxx...(truncated)"},
        ],
    }
