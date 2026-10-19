from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    control_plane_url: str = "http://127.0.0.1:8000"
    gateway_token: str = ""
    # Fresh decisions are fetched each request until this age, then reused if the
    # control plane blips. After stale_ttl the gateway fails closed.
    route_cache_ttl_seconds: float = 1.0
    route_stale_ttl_seconds: float = 30.0
    upstream_timeout_seconds: float = 10.0
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


def get_settings() -> Settings:
    return Settings()
