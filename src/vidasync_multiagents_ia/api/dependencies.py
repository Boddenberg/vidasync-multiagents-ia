from functools import lru_cache

from vidasync_multiagents_ia.config import get_settings
from vidasync_multiagents_ia.services import (
    AIRouterService,
    CaloriasTextoService,
    AudioTranscricaoService,
    FotoCaloriasPipelineTesteService,
    FotoAlimentosService,
    FrasePorcoesService,
    ImagemTextoService,
    OpenFoodFactsService,
    OpenAIChatService,
    OrchestratorService,
    PlanoImagemPipelineTesteService,
    PlanoPipelineE2ETesteService,
    PlanoTextoNormalizadoService,
    PdfTextoService,
    PlanoAlimentarService,
    TacoOnlineService,
    TBCAService,
)


@lru_cache(maxsize=1)
def get_openai_chat_service() -> OpenAIChatService:
    return OpenAIChatService(settings=get_settings())


@lru_cache(maxsize=1)
def get_calorias_texto_service() -> CaloriasTextoService:
    return CaloriasTextoService(settings=get_settings())


@lru_cache(maxsize=1)
def get_audio_transcricao_service() -> AudioTranscricaoService:
    return AudioTranscricaoService(settings=get_settings())


@lru_cache(maxsize=1)
def get_frase_porcoes_service() -> FrasePorcoesService:
    return FrasePorcoesService(settings=get_settings())


@lru_cache(maxsize=1)
def get_plano_alimentar_service() -> PlanoAlimentarService:
    return PlanoAlimentarService(settings=get_settings())


@lru_cache(maxsize=1)
def get_imagem_texto_service() -> ImagemTextoService:
    return ImagemTextoService(settings=get_settings())


@lru_cache(maxsize=1)
def get_pdf_texto_service() -> PdfTextoService:
    return PdfTextoService(settings=get_settings())


@lru_cache(maxsize=1)
def get_plano_texto_normalizado_service() -> PlanoTextoNormalizadoService:
    return PlanoTextoNormalizadoService(settings=get_settings())


@lru_cache(maxsize=1)
def get_plano_imagem_pipeline_teste_service() -> PlanoImagemPipelineTesteService:
    settings = get_settings()
    return PlanoImagemPipelineTesteService(settings=settings)


@lru_cache(maxsize=1)
def get_plano_pipeline_e2e_teste_service() -> PlanoPipelineE2ETesteService:
    settings = get_settings()
    return PlanoPipelineE2ETesteService(settings=settings)


@lru_cache(maxsize=1)
def get_orchestrator_service() -> OrchestratorService:
    return OrchestratorService()


@lru_cache(maxsize=1)
def get_tbca_service() -> TBCAService:
    return TBCAService()


@lru_cache(maxsize=1)
def get_taco_online_service() -> TacoOnlineService:
    return TacoOnlineService()


@lru_cache(maxsize=1)
def get_open_food_facts_service() -> OpenFoodFactsService:
    return OpenFoodFactsService()


@lru_cache(maxsize=1)
def get_foto_alimentos_service() -> FotoAlimentosService:
    return FotoAlimentosService(settings=get_settings())


@lru_cache(maxsize=1)
def get_foto_calorias_pipeline_teste_service() -> FotoCaloriasPipelineTesteService:
    settings = get_settings()
    return FotoCaloriasPipelineTesteService(
        settings=settings,
        foto_service=get_foto_alimentos_service(),
        calorias_service=get_calorias_texto_service(),
    )


@lru_cache(maxsize=1)
def get_ai_router_service() -> AIRouterService:
    settings = get_settings()
    return AIRouterService(
        settings=settings,
        openai_chat_service=get_openai_chat_service(),
        foto_alimentos_service=get_foto_alimentos_service(),
        audio_transcricao_service=get_audio_transcricao_service(),
        pdf_texto_service=get_pdf_texto_service(),
        calorias_texto_service=get_calorias_texto_service(),
    )
