from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ErrorBody(BaseModel):
    error: str
    message: str
    request_id: str
    details: list[dict] | None = None


class EnvironmentOut(BaseModel):
    id: str
    name: str
    provider: str
    region: str
    cluster_name: str
    kubernetes_version: str | None
    base_url: str
    role: str
    runtime: str
    verification: str
    experiments_allowed: bool
    enabled: bool
    notes: str
    state: str
    circuit: str
    eligible: bool
    consecutive_failures: int
    consecutive_successes: int
    consecutive_latency_breaches: int
    last_outcome: str | None
    last_detail: str | None
    last_latency_ms: float | None
    last_checked_at: datetime | None


class ServiceOut(BaseModel):
    id: str
    environment_id: str
    name: str
    analyse_path: str
    base_url: str
    state: str
    eligible: bool


class ObservationOut(BaseModel):
    id: int
    checked_at: datetime
    outcome: str
    latency_ms: float
    status_code: int | None
    detail: str


class IncidentEventOut(BaseModel):
    id: int
    occurred_at: datetime
    kind: str
    message: str
    evidence: dict


class IncidentOut(BaseModel):
    id: str
    status: str
    summary: str
    trigger: str
    started_at: datetime
    detected_at: datetime
    failure_window_started_at: datetime | None
    routing_changed_at: datetime | None
    resolved_at: datetime | None
    duration_seconds: float | None
    detection_seconds: float | None
    preferred_environment_id: str | None
    from_environment_id: str | None
    to_environment_id: str | None
    events: list[IncidentEventOut] = []


class RoutingOut(BaseModel):
    active_environment_id: str | None
    mode: str
    manual_environment_id: str | None
    preferred_environment_id: str | None
    switched_at: datetime | None
    cooldown_until: datetime | None
    reason: str
    generation: int
    active_base_url: str | None = None
    active_eligible: bool = False
    data_plane: str = "routing-gateway"


class OverrideIn(BaseModel):
    environment_id: str | None = Field(default=None, max_length=64)
    reason: str = Field(min_length=3, max_length=500)


class SettingsOut(BaseModel):
    health_check_interval_seconds: int
    failure_threshold: int
    success_threshold: int
    cooldown_seconds: int
    latency_threshold_ms: float
    latency_breach_threshold: int
    preferred_environment_id: str | None
    alert_error_rate: float
    alert_latency_ms: float
    recovery_policy: str


class SettingsIn(BaseModel):
    health_check_interval_seconds: int = Field(ge=2, le=300)
    failure_threshold: int = Field(ge=2, le=20)
    success_threshold: int = Field(ge=1, le=20)
    cooldown_seconds: int = Field(ge=5, le=3600)
    latency_threshold_ms: float = Field(ge=50, le=30_000)
    latency_breach_threshold: int = Field(ge=2, le=20)
    preferred_environment_id: str = Field(min_length=1, max_length=64)
    alert_error_rate: float = Field(ge=0, le=1)
    alert_latency_ms: float = Field(ge=50, le=30_000)
    recovery_policy: str

    @field_validator("recovery_policy")
    @classmethod
    def recovery_policy_known(cls, value: str) -> str:
        if value not in {"automatic", "manual"}:
            raise ValueError("recovery_policy must be automatic or manual")
        return value


class ExperimentIn(BaseModel):
    kind: str
    target_environment_id: str = Field(min_length=1, max_length=64)
    duration_seconds: int = Field(default=60, ge=1, le=300)
    latency_ms: int = Field(default=1200, ge=0, le=10_000)
    error_status: int = Field(default=500, ge=400, le=599)

    @field_validator("kind")
    @classmethod
    def kind_known(cls, value: str) -> str:
        allowed = {
            "inject_latency",
            "inject_errors",
            "fail_readiness",
            "fail_liveness",
            "clear_faults",
            "restart_local_pods",
        }
        if value not in allowed:
            raise ValueError(f"kind must be one of: {', '.join(sorted(allowed))}")
        return value


class ExperimentOut(BaseModel):
    id: str
    kind: str
    target_environment_id: str
    status: str
    requested_by: str
    parameters: dict
    result: dict | None
    started_at: datetime
    finished_at: datetime | None


class AuditOut(BaseModel):
    id: int
    occurred_at: datetime
    actor: str
    action: str
    resource: str
    detail: dict


class TrafficIn(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    environment_id: str = Field(min_length=1, max_length=64)
    status_code: int = Field(ge=0, le=599)
    latency_ms: float = Field(ge=0, le=120_000)
    path: str = Field(min_length=1, max_length=200)
    error: str | None = Field(default=None, max_length=120)


class MetricsSummary(BaseModel):
    window_seconds: int
    request_count: int
    error_count: int
    error_rate: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    alert_error_rate: float
    alert_latency_ms: float
    by_environment: list[dict]
    series: list[dict]
    measurement: str


class PodInventory(BaseModel):
    name: str
    phase: str
    ready: bool
    node: str | None
    app: str | None


class ClusterInventory(BaseModel):
    available: bool
    cluster_name: str
    kubernetes_version: str | None = None
    node_count: int = 0
    ready_node_count: int = 0
    pods: list[PodInventory] = []
    detail: str | None = None


class MetaOut(BaseModel):
    product: str
    version: str
    public_gateway_url: str
    data_plane: str
    dns_failover: bool
    limitations: list[str]


class WhoAmI(BaseModel):
    actor: str
    role: str


class EnvironmentPage(BaseModel):
    items: list[EnvironmentOut]
    total: int
    limit: int
    offset: int


class ServicePage(BaseModel):
    items: list[ServiceOut]
    total: int
    limit: int
    offset: int


class IncidentPage(BaseModel):
    items: list[IncidentOut]
    total: int
    limit: int
    offset: int


class ExperimentPage(BaseModel):
    items: list[ExperimentOut]
    total: int
    limit: int
    offset: int


class AuditPage(BaseModel):
    items: list[AuditOut]
    total: int
    limit: int
    offset: int


class ObservationPage(BaseModel):
    items: list[ObservationOut]
    total: int
    limit: int
    offset: int
