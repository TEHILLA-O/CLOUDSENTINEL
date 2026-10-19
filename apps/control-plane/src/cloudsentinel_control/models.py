from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(32))
    region: Mapped[str] = mapped_column(String(64))
    cluster_name: Mapped[str] = mapped_column(String(120))
    kubernetes_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    base_url: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(32))
    # local_container and kind are runnable here. aks/gke are records until a cluster exists.
    runtime: Mapped[str] = mapped_column(String(32))
    verification: Mapped[str] = mapped_column(String(64), default="not_cloud_verified")
    experiments_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    environment_id: Mapped[str] = mapped_column(ForeignKey("environments.id"))
    name: Mapped[str] = mapped_column(String(120))
    analyse_path: Mapped[str] = mapped_column(String(120), default="/api/v1/analyse")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EnvironmentHealth(Base):
    __tablename__ = "environment_health"

    environment_id: Mapped[str] = mapped_column(ForeignKey("environments.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), default="unknown")
    circuit: Mapped[str] = mapped_column(String(32), default="closed")
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_successes: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_latency_breaches: Mapped[int] = mapped_column(Integer, default=0)
    last_outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HealthObservation(Base):
    __tablename__ = "health_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment_id: Mapped[str] = mapped_column(ForeignKey("environments.id"), index=True)
    service_id: Mapped[str] = mapped_column(String(64))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    outcome: Mapped[str] = mapped_column(String(64))
    latency_ms: Mapped[float] = mapped_column(Float)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")


class RoutingState(Base):
    __tablename__ = "routing_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_environment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), default="automatic")
    manual_environment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_environment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    switched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    generation: Mapped[int] = mapped_column(Integer, default=0)


class RuntimeSettings(Base):
    __tablename__ = "runtime_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    health_check_interval_seconds: Mapped[int] = mapped_column(Integer, default=5)
    failure_threshold: Mapped[int] = mapped_column(Integer, default=3)
    success_threshold: Mapped[int] = mapped_column(Integer, default=2)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=30)
    latency_threshold_ms: Mapped[float] = mapped_column(Float, default=800)
    latency_breach_threshold: Mapped[int] = mapped_column(Integer, default=3)
    preferred_environment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    alert_error_rate: Mapped[float] = mapped_column(Float, default=0.05)
    alert_latency_ms: Mapped[float] = mapped_column(Float, default=800)
    recovery_policy: Mapped[str] = mapped_column(String(32), default="automatic")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    failure_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    routing_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preferred_environment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_environment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_environment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class TrafficSample(Base):
    __tablename__ = "traffic_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    environment_id: Mapped[str] = mapped_column(String(64), index=True)
    status_code: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[float] = mapped_column(Float)
    path: Mapped[str] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ExperimentRecord(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))
    target_environment_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    requested_by: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(120))
    resource: Mapped[str] = mapped_column(String(200))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
