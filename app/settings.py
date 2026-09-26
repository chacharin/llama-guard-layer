from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    guard_model: str = "meta-llama/llama-guard-4-12b"
    request_timeout_seconds: float = 20.0

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    cors_allowed_origins: str = "*"

    blocklist_path: str = "blocklist.txt"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
