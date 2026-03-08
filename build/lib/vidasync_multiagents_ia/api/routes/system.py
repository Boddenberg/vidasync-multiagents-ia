from fastapi import APIRouter, Depends, Response

from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.observability import render_metrics_prometheus

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/metrics")
def metrics(settings: Settings = Depends(get_settings)) -> Response:
    if not settings.metrics_enabled:
        return Response(status_code=404, content="metrics_disabled\n", media_type="text/plain; version=0.0.4")
    content = render_metrics_prometheus()
    return Response(content=content, media_type="text/plain; version=0.0.4")
