from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3.5-flash"
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
