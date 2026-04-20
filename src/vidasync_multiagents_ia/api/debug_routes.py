"""Wiring for debug/manual-test routes gated by ``debug_local_routes_enabled``.

Kept in a dedicated module so that the production router never imports
these endpoints transitively unless the feature flag is on.
"""
from fastapi import APIRouter

from vidasync_multiagents_ia.config import Settings


def include_debug_routes(api_router: APIRouter, settings: Settings) -> None:
    if not settings.debug_local_routes_enabled:
        return
    from vidasync_multiagents_ia.api.routes.foto_calorias_pipeline_teste import (
        router as foto_calorias_pipeline_teste_router,
    )
    from vidasync_multiagents_ia.api.routes.plano_imagem_pipeline_teste import (
        router as plano_imagem_pipeline_teste_router,
    )
    from vidasync_multiagents_ia.api.routes.plano_pipeline_e2e_teste import (
        router as plano_pipeline_e2e_teste_router,
    )

    api_router.include_router(foto_calorias_pipeline_teste_router)
    api_router.include_router(plano_imagem_pipeline_teste_router)
    api_router.include_router(plano_pipeline_e2e_teste_router)
