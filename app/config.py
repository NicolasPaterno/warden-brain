from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    app_env: str = "local"
    log_level: str = "INFO"
    auth_base_url: str = "http://localhost:8082"
    gateway_base_url: str = "http://localhost:8080"
    brain_client_id: str = ""
    brain_client_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
