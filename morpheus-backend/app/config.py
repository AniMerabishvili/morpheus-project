from typing import Optional

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
    # True  → load Whisper/spaCy/sentence-transformers locally (dev only)
    # False → use cloud APIs for transcription & embeddings (production)
    USE_LOCAL_MODELS: bool = False
    # Transcription provider when USE_LOCAL_MODELS=False:
    #   "groq"   → Groq Whisper large-v3 (recommended: best quality, free, fast)
    #   "gemini" → Gemini inline audio (fallback when no GROQ_API_KEY)
    WHISPER_PROVIDER: str = "groq"
    # Groq API key — required when WHISPER_PROVIDER=groq.
    # Get a free key at console.groq.com (no credit card needed).
    GROQ_API_KEY: Optional[str] = None
    # Field-level encryption key for sensitive dream columns (raw_text, analysis, title).
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # If unset, fields are stored as plaintext (safe for local dev; always set in production).
    DREAM_ENCRYPTION_KEY: Optional[str] = None
    # Comma-separated list of allowed frontend origins, e.g. https://morpheus-app.vercel.app
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
