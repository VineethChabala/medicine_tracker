from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://tracker_admin:secret123@localhost:5432/medicine_tracker"

    # JWT Auth
    jwt_secret: str = "changeme_use_a_real_secret_in_production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Telegram
    telegram_bot_token: str = ""
    webhook_url: str = ""

    # Google Gemini
    gemini_api_key: str = ""

    # Layer 3 web search uses DuckDuckGo (duckduckgo-search library)
    # No API key needed — completely free


settings = Settings()
