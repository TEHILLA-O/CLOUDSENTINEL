from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_version: str = "0.1.0"
    database_url: str = "sqlite+aiosqlite:///./data/control-plane.db"
    admin_token: str = ""
    reader_token: str = ""
    gateway_token: str = ""
    fault_token: str = ""
    analysis_azure_url: str = "http://127.0.0.1:8001"
    analysis_gcp_url: str = "http://127.0.0.1:8002"
    public_gateway_url: str = "http://127.0.0.1:8081"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    monitor_enabled: bool = True
    probe_timeout_seconds: float = 2.0
    log_level: str = "INFO"
    # Restart experiments are off until an operator points them at a named kind context.
    kubectl_restart_enabled: bool = False
    kubectl_context: str = "kind-cloudsentinel"
    kubectl_namespace: str = "cloudsentinel"
    # JSON object of environment id -> deployment name. User input never becomes a shell string.
    kubectl_restart_map: str = "{}"
    allow_cloud_experiments: bool = False
    # Operator identity for the two analysis services. Provider stays "local"
    # until the process is actually registered in that cloud.
    cluster_runtime: str = "local_container"
    cluster_name: str = ""
    cluster_inventory_enabled: bool = False
    primary_name: str = "Primary"
    secondary_name: str = "Secondary"
    primary_provider: str = "local"
    secondary_provider: str = "local"
    primary_region: str = "local"
    secondary_region: str = "local"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


def get_settings() -> Settings:
    return Settings()
