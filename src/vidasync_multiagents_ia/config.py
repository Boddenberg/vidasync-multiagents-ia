from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_audio_model: str = "gpt-4o-mini-transcribe"
    audio_max_upload_bytes: int = 8 * 1024 * 1024
    audio_recommended_max_seconds: int = 45
    pdf_max_upload_bytes: int = 20 * 1024 * 1024
    supabase_url: str = ""
    supabase_storage_public_bucket: str = "pipeline-inputs"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    chroma_persist_dir: str = ".chroma"
    vidasync_docs_dir: str = "knowledge"
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 120
    rag_top_k: int = 4
    rag_min_score: float = 0.12
    rag_context_max_chars: int = 4000
    rag_embedding_provider: str = "auto"
    rag_embedding_model: str = "text-embedding-3-small"
    chat_memory_enabled: bool = True
    chat_memory_max_turns_short_term: int = 8
    chat_memory_summary_max_chars: int = 1800
    chat_memory_context_max_chars: int = 2200
    chat_memory_max_turn_chars: int = 320
    log_level: str = "INFO"
    log_format: str = "json"
    log_json_pretty: bool = False
    log_http_headers: bool = False
    log_http_max_body_bytes: int = 32768
    log_http_max_body_chars: int = 4000
    metrics_enabled: bool = True
    response_exclude_none: bool = False
    openai_timeout_seconds: float = 60.0
    plano_alimentar_refeicoes_second_pass_enabled: bool = False
    plano_pipeline_orchestrator_engine: str = "langgraph"
    chat_orchestrator_engine: str = "langgraph"
    debug_local_routes_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
