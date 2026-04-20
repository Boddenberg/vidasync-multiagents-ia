from functools import lru_cache

from vidasync_multiagents_ia.clients import OpenFoodFactsClient, TacoOnlineClient, TBCAClient
from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.core.retry import RetryConfig
from vidasync_multiagents_ia.services import (
    AIRouterService,
    AudioTranscricaoService,
    CaloriasTextoService,
    FotoAlimentosService,
    FotoCaloriasPipelineTesteService,
    FrasePorcoesService,
    ImagemTextoService,
    NutriChatService,
    OpenAIChatService,
    OpenFoodFactsService,
    PdfTextoService,
    PlanoAlimentarService,
    PlanoImagemPipelineTesteService,
    PlanoPipelineE2ETesteService,
    PlanoTextoNormalizadoService,
    TacoOnlineService,
    TBCAService,
)


@lru_cache(maxsize=1)
def get_openai_chat_service() -> OpenAIChatService:
    return OpenAIChatService(settings=get_settings())


@lru_cache(maxsize=1)
def get_nutri_chat_service() -> NutriChatService:
    return NutriChatService(
        settings=get_settings(),
        openai_chat_service=get_openai_chat_service(),
    )


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


def _build_retry_config(settings: Settings) -> RetryConfig:
    return RetryConfig(
        max_attempts=settings.external_http_retry_max_attempts,
        base_delay_seconds=settings.external_http_retry_base_delay_seconds,
        max_delay_seconds=settings.external_http_retry_max_delay_seconds,
        jitter_factor=settings.external_http_retry_jitter_factor,
    )


@lru_cache(maxsize=1)
def get_tbca_service() -> TBCAService:
    settings = get_settings()
    return TBCAService(
        client=TBCAClient(
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
            cache_ttl_seconds=settings.external_http_cache_ttl_seconds,
            cache_max_entries=settings.external_http_cache_max_entries,
            circuit_failure_threshold=settings.external_http_circuit_failure_threshold,
            circuit_recovery_seconds=settings.external_http_circuit_recovery_seconds,
            retry_config=_build_retry_config(settings),
        )
    )


@lru_cache(maxsize=1)
def get_taco_online_service() -> TacoOnlineService:
    settings = get_settings()
    return TacoOnlineService(
        client=TacoOnlineClient(
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
            cache_ttl_seconds=settings.external_http_cache_ttl_seconds,
            cache_max_entries=settings.external_http_cache_max_entries,
            circuit_failure_threshold=settings.external_http_circuit_failure_threshold,
            circuit_recovery_seconds=settings.external_http_circuit_recovery_seconds,
            retry_config=_build_retry_config(settings),
        )
    )


@lru_cache(maxsize=1)
def get_open_food_facts_service() -> OpenFoodFactsService:
    settings = get_settings()
    return OpenFoodFactsService(
        client=OpenFoodFactsClient(
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
            cache_ttl_seconds=settings.external_http_cache_ttl_seconds,
            cache_max_entries=settings.external_http_cache_max_entries,
            circuit_failure_threshold=settings.external_http_circuit_failure_threshold,
            circuit_recovery_seconds=settings.external_http_circuit_recovery_seconds,
            retry_config=_build_retry_config(settings),
        )
    )


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
        tbca_service=get_tbca_service(),
        taco_online_service=get_taco_online_service(),
        imagem_texto_service=get_imagem_texto_service(),
        plano_texto_normalizado_service=get_plano_texto_normalizado_service(),
        plano_alimentar_service=get_plano_alimentar_service(),
        frase_porcoes_service=get_frase_porcoes_service(),
    )
