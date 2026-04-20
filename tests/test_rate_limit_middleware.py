from fastapi import FastAPI
from fastapi.testclient import TestClient

from vidasync_multiagents_ia.core.rate_limit import (
    InMemoryTokenBucketRateLimiter,
    TokenBucketConfig,
)
from vidasync_multiagents_ia.observability import apply_rate_limit


def _build_app(*, capacity: float, refill: float, exempt: tuple[str, ...] = ("/health",)) -> FastAPI:
    app = FastAPI()
    limiter = InMemoryTokenBucketRateLimiter(TokenBucketConfig(capacity=capacity, refill_per_second=refill))

    @app.middleware("http")
    async def _mw(request, call_next):
        return await apply_rate_limit(
            request,
            call_next,
            limiter=limiter,
            exempt_paths=exempt,
        )

    @app.get("/echo")
    def echo() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_rate_limit_allows_up_to_capacity_then_returns_429() -> None:
    app = _build_app(capacity=2, refill=0.01)
    client = TestClient(app)

    assert client.get("/echo").status_code == 200
    assert client.get("/echo").status_code == 200
    blocked = client.get("/echo")
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after")
    assert blocked.json()["detail"].startswith("Limite")


def test_rate_limit_exempts_configured_paths() -> None:
    app = _build_app(capacity=1, refill=0.01, exempt=("/health",))
    client = TestClient(app)
    client.get("/echo")
    assert client.get("/echo").status_code == 429
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_rate_limit_adds_remaining_header_on_allowed_requests() -> None:
    app = _build_app(capacity=5, refill=1)
    client = TestClient(app)
    response = client.get("/echo")
    assert response.status_code == 200
    assert "x-ratelimit-remaining" in {key.lower() for key in response.headers.keys()}
