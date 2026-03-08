from fastapi import APIRouter

from vidasync_multiagents_ia.config import get_settings
from vidasync_multiagents_ia.api.routes.ai_router import router as ai_router_router
from vidasync_multiagents_ia.api.routes.audio_transcricao import router as audio_transcricao_router
from vidasync_multiagents_ia.api.routes.foto_calorias_pipeline_teste import (
    router as foto_calorias_pipeline_teste_router,
)
from vidasync_multiagents_ia.api.routes.foto_alimentos import router as foto_alimentos_router
from vidasync_multiagents_ia.api.routes.frase_porcoes import router as frase_porcoes_router
from vidasync_multiagents_ia.api.routes.imagem_texto import router as imagem_texto_router
from vidasync_multiagents_ia.api.routes.openai_chat import router as openai_chat_router
from vidasync_multiagents_ia.api.routes.orchestrator import router as orchestrator_router
from vidasync_multiagents_ia.api.routes.plano_imagem_pipeline_teste import (
    router as plano_imagem_pipeline_teste_router,
)
from vidasync_multiagents_ia.api.routes.plano_pipeline_e2e_teste import (
    router as plano_pipeline_e2e_teste_router,
)
from vidasync_multiagents_ia.api.routes.plano_texto_normalizado import (
    router as plano_texto_normalizado_router,
)
from vidasync_multiagents_ia.api.routes.pdf_texto import router as pdf_texto_router
from vidasync_multiagents_ia.api.routes.plano_alimentar import router as plano_alimentar_router
from vidasync_multiagents_ia.api.routes.system import router as system_router
from vidasync_multiagents_ia.api.routes.taco_online import router as taco_online_router
from vidasync_multiagents_ia.api.routes.tbca import router as tbca_router

api_router = APIRouter()
settings = get_settings()
api_router.include_router(system_router)
api_router.include_router(ai_router_router)
api_router.include_router(orchestrator_router)
api_router.include_router(openai_chat_router)
api_router.include_router(audio_transcricao_router)
api_router.include_router(frase_porcoes_router)
api_router.include_router(plano_alimentar_router)
api_router.include_router(imagem_texto_router)
api_router.include_router(pdf_texto_router)
api_router.include_router(plano_texto_normalizado_router)
if settings.debug_local_routes_enabled:
    api_router.include_router(foto_calorias_pipeline_teste_router)
    api_router.include_router(plano_imagem_pipeline_teste_router)
    api_router.include_router(plano_pipeline_e2e_teste_router)
api_router.include_router(tbca_router)
api_router.include_router(taco_online_router)
api_router.include_router(foto_alimentos_router)
