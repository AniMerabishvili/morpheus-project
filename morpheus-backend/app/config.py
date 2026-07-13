from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GRAPH_LOCAL_SIMILARITY_THRESHOLD: float = 0.65
    GRAPH_CLOUD_SIMILARITY_THRESHOLD: float = 0.78
    GRAPH_CLOUD_STRICT_SIMILARITY_THRESHOLD: float = 0.88
    # OPENAI_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    WHISPER_MODEL: str = "medium"
    # True  → load Whisper/spaCy/sentence-transformers locally (Mac dev)
    # False → use Gemini APIs for transcription & embeddings (Railway cloud)
    USE_LOCAL_MODELS: bool = False
    # Comma-separated list of allowed frontend origins, e.g. https://morpheus-app.up.railway.app
    # Leave empty to allow all origins (development default).
    ALLOWED_ORIGINS: str = ""
    MAX_DREAM_TEXT_CHARS: int = 20000
    MAX_TEXT_REQUEST_BYTES: int = 262144
    MAX_AUDIO_UPLOAD_BYTES: int = 10485760
    PROCESS_RATE_LIMIT_REQUESTS: int = 5
    PROCESS_RATE_LIMIT_WINDOW_SECONDS: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
