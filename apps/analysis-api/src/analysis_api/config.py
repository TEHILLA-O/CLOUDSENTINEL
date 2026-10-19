from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets arrive through the environment, never the image."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_version: str = "0.1.0"
    environment_name: str = "local"
    environment_provider: str = "local"
    # deterministic works with no credentials. openai is opt-in.
    analysis_backend: str = "deterministic"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_timeout_seconds: float = 8.0
    max_body_bytes: int = 65_536
    fault_injection_enabled: bool = False
    fault_token: str = ""
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
