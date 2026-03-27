from types import SimpleNamespace

from vidasync_multiagents_ia.clients.openai_client import OpenAIClient
from vidasync_multiagents_ia.config import Settings


class _FakeResponses:
    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["model"] == "gpt-4o-mini"
        assert kwargs["input"] == "teste de telemetria"
        return SimpleNamespace(
            id="resp_123",
            output_text="resposta pronta",
            usage=SimpleNamespace(
                input_tokens=120,
                output_tokens=30,
                total_tokens=150,
                input_tokens_details=SimpleNamespace(cached_tokens=20),
            ),
        )


class _FakeOpenAISdk:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


def test_openai_client_registra_usage_e_custo(monkeypatch) -> None:
    captured = {}

    monkeypatch.setattr(
        "vidasync_multiagents_ia.clients.openai_client.get_settings",
        lambda: Settings(
            telemetry_store_previews=True,
            telemetry_openai_pricing_by_model={
                "gpt-4o-mini": {
                    "input_per_million": 0.15,
                    "cached_input_per_million": 0.075,
                    "output_per_million": 0.60,
                }
            },
        ),
    )
    monkeypatch.setattr(
        "vidasync_multiagents_ia.clients.openai_client.record_llm_call",
        lambda **kwargs: captured.update(kwargs),
    )

    client = OpenAIClient(api_key="test-key", timeout_seconds=5)
    client._client = _FakeOpenAISdk()  # type: ignore[assignment]

    output = client.generate_text(model="gpt-4o-mini", prompt="teste de telemetria")

    assert output == "resposta pronta"
    assert captured["provider"] == "openai"
    assert captured["operation"] == "generate_text"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["provider_response_id"] == "resp_123"
    assert captured["input_tokens"] == 120
    assert captured["output_tokens"] == 30
    assert captured["total_tokens"] == 150
    assert captured["cost_usd"] == 0.0000345
    assert captured["status"] == "ok"
