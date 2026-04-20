from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.observability import render_metrics_prometheus

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(settings: Settings = Depends(get_settings)) -> Response:
    checks = _collect_readiness_checks(settings)
    ready_ok = all(check["ok"] for check in checks.values())
    payload = {"status": "ready" if ready_ok else "not_ready", "checks": checks}
    return JSONResponse(status_code=200 if ready_ok else 503, content=payload)


@router.get("/metrics")
def metrics(settings: Settings = Depends(get_settings)) -> Response:
    if not settings.metrics_enabled:
        return Response(status_code=404, content="metrics_disabled\n", media_type="text/plain; version=0.0.4")
    content = render_metrics_prometheus()
    return Response(content=content, media_type="text/plain; version=0.0.4")


def _collect_readiness_checks(settings: Settings) -> dict[str, dict[str, object]]:
    checks: dict[str, dict[str, object]] = {}

    openai_ok = bool((settings.openai_api_key or "").strip())
    checks["openai_api_key"] = {
        "ok": openai_ok,
        "detail": "present" if openai_ok else "missing",
    }

    supabase_configured = bool((settings.supabase_url or "").strip())
    supabase_keys_ok = (
        not supabase_configured
        or bool((settings.supabase_anon_key or "").strip())
        or bool((settings.supabase_service_role_key or "").strip())
    )
    checks["supabase"] = {
        "ok": supabase_keys_ok,
        "detail": "configured" if supabase_configured else "not_configured",
    }

    return checks
