from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    llm_host: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    app_env: str = "local"
    log_level: str = "INFO"
    auth_base_url: str = "http://localhost:8082"
    gateway_base_url: str = "http://localhost:8080"
    brain_client_id: str = ""
    brain_client_secret: str = ""
    jwt_issuer: str = "warden-auth"
    jwt_audience: str = "warden-brain"
    jwt_jwks_path: str = "/.well-known/jwks.json"

    # Observability (Phase 5). Empty OTLP endpoint disables tracing (local dev).
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "warden-brain"

    @property
    def jwks_url(self) -> str:
        return f"{self.auth_base_url.rstrip('/')}{self.jwt_jwks_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
