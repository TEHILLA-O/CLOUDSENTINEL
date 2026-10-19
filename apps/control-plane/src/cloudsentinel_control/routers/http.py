import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cloudsentinel_control.auth import Actor, require_admin, require_gateway, require_reader, require_routing_client
from cloudsentinel_control.config import Settings
from cloudsentinel_control.experiments import run_experiment
from cloudsentinel_control.reliability.monitor import run_monitor_tick
from cloudsentinel_control.models import (
    AuditEvent,
    Environment,
    EnvironmentHealth,
    ExperimentRecord,
    HealthObservation,
    Incident,
    IncidentEvent,
    RoutingState,
    RuntimeSettings,
    Service,
    TrafficSample,
)
from cloudsentinel_control.schemas import (
    AuditPage,
    EnvironmentOut,
    EnvironmentPage,
    ExperimentOut,
    ExperimentPage,
    IncidentEventOut,
    IncidentOut,
    IncidentPage,
    MetaOut,
    MetricsSummary,
    ObservationOut,
    ObservationPage,
    OverrideIn,
    RoutingOut,
    ServiceOut,
    ServicePage,
    SettingsIn,
    SettingsOut,
    TrafficIn,
    WhoAmI,
    ExperimentIn,
)

def bind(settings: Settings) -> APIRouter:
    router = APIRouter()
    reader = require_reader(settings)
    admin = require_admin(settings)
    gateway = require_gateway(settings)
    routing_client = require_routing_client(settings)

    @router.get("/health/live", tags=["health"])
    async def live():
        return {"status": "alive"}

    @router.get("/health/ready", tags=["health"])
    async def ready(session: AsyncSession = Depends(get_session)):
        await session.execute(text("SELECT 1"))
        return {"status": "ready"}

    @router.get("/api/v1/meta", response_model=MetaOut, tags=["meta"])
    async def meta():
        return MetaOut(
            product="CloudSentinel",
            version=settings.app_version,
            public_gateway_url=settings.public_gateway_url,
            data_plane="routing-gateway",
            dns_failover=False,
            limitations=[
                "The gateway is a single process. It is not global DNS failover.",
                "Azure and GCP names on local environments are labels, not cloud deployments.",
                "A control-plane restart resumes from the database; in-flight probes are repeated.",
            ],
        )

    @router.get("/api/v1/whoami", response_model=WhoAmI, tags=["meta"])
    async def whoami(actor: Actor = Depends(reader)):
        return WhoAmI(actor=actor.name, role=actor.role)

    @router.get("/api/v1/environments", response_model=EnvironmentPage, tags=["environments"])
    async def list_environments(
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(reader),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        total = await session.scalar(select(func.count()).select_from(Environment))
        rows = list(await session.scalars(select(Environment).order_by(Environment.id).limit(limit).offset(offset)))
        return EnvironmentPage(
            items=[await _environment_out(session, row) for row in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    @router.get("/api/v1/environments/{environment_id}", response_model=EnvironmentOut, tags=["environments"])
    async def get_environment(environment_id: str, session: AsyncSession = Depends(get_session), actor: Actor = Depends(reader)):
        row = await session.get(Environment, environment_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Environment was not found.")
        return await _environment_out(session, row)

    @router.get("/api/v1/services", response_model=ServicePage, tags=["services"])
    async def list_services(
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(reader),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        total = await session.scalar(select(func.count()).select_from(Service))
        rows = list(await session.scalars(select(Service).order_by(Service.id).limit(limit).offset(offset)))
        items = []
        for row in rows:
            environment = await session.get(Environment, row.environment_id)
            health = await session.get(EnvironmentHealth, row.environment_id)
            items.append(
                ServiceOut(
                    id=row.id,
                    environment_id=row.environment_id,
                    name=row.name,
                    analyse_path=row.analyse_path,
                    base_url=environment.base_url if environment else "",
                    state=health.state if health else "unknown",
                    eligible=health.eligible if health else False,
                )
            )
        return ServicePage(items=items, total=total or 0, limit=limit, offset=offset)

    @router.get("/api/v1/services/{service_id}/health", response_model=ObservationPage, tags=["services"])
    async def service_health(
        service_id: str,
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(reader),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        service = await session.get(Service, service_id)
        if service is None:
            raise HTTPException(status_code=404, detail="Service was not found.")
        query = select(HealthObservation).where(HealthObservation.service_id == service_id)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = list(
            await session.scalars(query.order_by(HealthObservation.checked_at.desc()).limit(limit).offset(offset))
        )
        return ObservationPage(
            items=[
                ObservationOut(
                    id=row.id,
                    checked_at=_aware(row.checked_at),
                    outcome=row.outcome,
                    latency_ms=row.latency_ms,
                    status_code=row.status_code,
                    detail=row.detail,
                )
                for row in rows
            ],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    @router.get("/api/v1/incidents", response_model=IncidentPage, tags=["incidents"])
    async def list_incidents(
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(reader),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        total = await session.scalar(select(func.count()).select_from(Incident))
        rows = list(await session.scalars(select(Incident).order_by(Incident.started_at.desc()).limit(limit).offset(offset)))
        return IncidentPage(
            items=[_incident_out(row) for row in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    @router.get("/api/v1/incidents/{incident_id}", response_model=IncidentOut, tags=["incidents"])
    async def get_incident(incident_id: str, session: AsyncSession = Depends(get_session), actor: Actor = Depends(reader)):
        row = await session.get(Incident, incident_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Incident was not found.")
        events = list(
            await session.scalars(
                select(IncidentEvent).where(IncidentEvent.incident_id == incident_id).order_by(IncidentEvent.id)
            )
        )
        return _incident_out(row, events)

    @router.get("/api/v1/routing/current", response_model=RoutingOut, tags=["routing"])
    async def current_route(session: AsyncSession = Depends(get_session), actor: Actor = Depends(routing_client)):
        routing = await _routing(session)
        return await _routing_out(session, routing)

    @router.post("/api/v1/routing/override", response_model=RoutingOut, tags=["routing"])
    async def override_route(
        body: OverrideIn,
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(admin),
    ):
        routing = await _routing(session)
        settings_row = await _runtime_settings(session)
        now = datetime.now(timezone.utc)
        if body.environment_id is None:
            routing.mode = "automatic"
            routing.manual_environment_id = None
            routing.reason = body.reason
        else:
            environment = await session.get(Environment, body.environment_id)
            health = await session.get(EnvironmentHealth, body.environment_id)
            if environment is None or health is None:
                raise HTTPException(status_code=404, detail="Environment was not found.")
            if not health.eligible:
                raise HTTPException(status_code=409, detail="Refusing to send traffic to an environment that is not eligible.")
            routing.mode = "manual"
            routing.manual_environment_id = environment.id
            routing.active_environment_id = environment.id
            routing.switched_at = now
            routing.cooldown_until = now + timedelta(seconds=settings_row.cooldown_seconds)
            routing.generation += 1
            routing.reason = body.reason
        await _audit(session, actor.name, "routing.override", "routing/current", {"environment_id": body.environment_id, "reason": body.reason})
        return await _routing_out(session, routing)

    @router.post("/api/v1/routing/recover", response_model=RoutingOut, tags=["routing"])
    async def recover_route(session: AsyncSession = Depends(get_session), actor: Actor = Depends(admin)):
        """Clear a manual hold and the cooldown. The next probe decides whether to move."""
        routing = await _routing(session)
        routing.mode = "automatic"
        routing.manual_environment_id = None
        routing.cooldown_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        routing.reason = "Operator requested recovery to the preferred environment."
        await _audit(session, actor.name, "routing.recover", "routing/current", {})
        return await _routing_out(session, routing)

    @router.get("/api/v1/settings", response_model=SettingsOut, tags=["settings"])
    async def get_settings_route(session: AsyncSession = Depends(get_session), actor: Actor = Depends(reader)):
        return SettingsOut.model_validate(await _runtime_settings(session), from_attributes=True)

    @router.put("/api/v1/settings", response_model=SettingsOut, tags=["settings"])
    async def put_settings(
        body: SettingsIn,
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(admin),
    ):
        environment = await session.get(Environment, body.preferred_environment_id)
        if environment is None:
            raise HTTPException(status_code=422, detail="Preferred environment does not exist.")
        current = await _runtime_settings(session)
        for field, value in body.model_dump().items():
            setattr(current, field, value)
        routing = await _routing(session)
        routing.preferred_environment_id = body.preferred_environment_id
        await _audit(session, actor.name, "settings.update", "settings", body.model_dump())
        return SettingsOut.model_validate(current, from_attributes=True)

    @router.post("/api/v1/experiments", response_model=ExperimentOut, tags=["experiments"])
    async def create_experiment(
        body: ExperimentIn,
        request: Request,
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(admin),
    ):
        record = await run_experiment(session, settings, actor.name, body, request.app.state.http)
        await _audit(
            session,
            actor.name,
            "experiment.create",
            f"experiments/{record.id}",
            {"kind": body.kind, "target_environment_id": body.target_environment_id, "status": record.status},
        )
        return _experiment_out(record)

    @router.get("/api/v1/experiments/{experiment_id}", response_model=ExperimentOut, tags=["experiments"])
    async def get_experiment(experiment_id: str, session: AsyncSession = Depends(get_session), actor: Actor = Depends(reader)):
        row = await session.get(ExperimentRecord, experiment_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Experiment was not found.")
        return _experiment_out(row)

    @router.get("/api/v1/experiments", response_model=ExperimentPage, tags=["experiments"])
    async def list_experiments(
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(reader),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        total = await session.scalar(select(func.count()).select_from(ExperimentRecord))
        rows = list(
            await session.scalars(select(ExperimentRecord).order_by(ExperimentRecord.started_at.desc()).limit(limit).offset(offset))
        )
        return ExperimentPage(items=[_experiment_out(row) for row in rows], total=total or 0, limit=limit, offset=offset)

    @router.get("/api/v1/audit-events", response_model=AuditPage, tags=["audit"])
    async def list_audit(
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(admin),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        total = await session.scalar(select(func.count()).select_from(AuditEvent))
        rows = list(await session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit).offset(offset)))
        return AuditPage(
            items=[
                AuditOut(
                    id=row.id,
                    occurred_at=_aware(row.occurred_at),
                    actor=row.actor,
                    action=row.action,
                    resource=row.resource,
                    detail=row.detail or {},
                )
                for row in rows
            ],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    @router.post("/api/v1/monitor/tick", response_model=RoutingOut, tags=["routing"])
    async def tick_now(request: Request, session: AsyncSession = Depends(get_session), actor: Actor = Depends(admin)):
        """Run one probe cycle immediately. The background loop does the same work on its interval."""
        await run_monitor_tick(session, request.app.state.http, settings.probe_timeout_seconds)
        await _audit(session, actor.name, "monitor.tick", "routing/current", {})
        return await _routing_out(session, await _routing(session))

    @router.get("/api/v1/metrics/summary", response_model=MetricsSummary, tags=["metrics"])
    async def metrics_summary(
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(reader),
        window_seconds: int = Query(900, ge=60, le=86_400),
    ):
        runtime = await _runtime_settings(session)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        rows = list(await session.scalars(select(TrafficSample).where(TrafficSample.recorded_at >= cutoff)))
        return _summarise(rows, window_seconds, runtime)

    @router.post("/internal/traffic", status_code=204, tags=["internal"])
    async def record_traffic(
        body: TrafficIn,
        session: AsyncSession = Depends(get_session),
        actor: Actor = Depends(gateway),
    ):
        session.add(
            TrafficSample(
                recorded_at=datetime.now(timezone.utc),
                request_id=body.request_id,
                environment_id=body.environment_id,
                status_code=body.status_code,
                latency_ms=body.latency_ms,
                path=body.path,
                error=body.error,
            )
        )
        return None

    return router


async def get_session(request: Request):
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _environment_out(session: AsyncSession, row: Environment) -> EnvironmentOut:
    health = await session.get(EnvironmentHealth, row.id)
    return EnvironmentOut(
        id=row.id,
        name=row.name,
        provider=row.provider,
        region=row.region,
        cluster_name=row.cluster_name,
        kubernetes_version=row.kubernetes_version,
        base_url=row.base_url,
        role=row.role,
        runtime=row.runtime,
        verification=row.verification,
        experiments_allowed=row.experiments_allowed,
        enabled=row.enabled,
        notes=row.notes,
        state=health.state if health else "unknown",
        circuit=health.circuit if health else "closed",
        eligible=health.eligible if health else False,
        consecutive_failures=health.consecutive_failures if health else 0,
        consecutive_successes=health.consecutive_successes if health else 0,
        consecutive_latency_breaches=health.consecutive_latency_breaches if health else 0,
        last_outcome=health.last_outcome if health else None,
        last_detail=health.last_detail if health else None,
        last_latency_ms=health.last_latency_ms if health else None,
        last_checked_at=_aware(health.last_checked_at) if health else None,
    )


def _incident_out(row: Incident, events: list[IncidentEvent] | None = None) -> IncidentOut:
    started = _aware(row.started_at)
    resolved = _aware(row.resolved_at)
    changed = _aware(row.routing_changed_at)
    window = _aware(row.failure_window_started_at)
    end = resolved or datetime.now(timezone.utc)
    duration = (end - started).total_seconds() if started else None
    detection = (changed - window).total_seconds() if changed and window else None
    return IncidentOut(
        id=row.id,
        status=row.status,
        summary=row.summary,
        trigger=row.trigger,
        started_at=started,
        detected_at=_aware(row.detected_at),
        failure_window_started_at=window,
        routing_changed_at=changed,
        resolved_at=resolved,
        duration_seconds=round(duration, 3) if duration is not None else None,
        detection_seconds=round(detection, 3) if detection is not None else None,
        preferred_environment_id=row.preferred_environment_id,
        from_environment_id=row.from_environment_id,
        to_environment_id=row.to_environment_id,
        events=[
            IncidentEventOut(
                id=event.id,
                occurred_at=_aware(event.occurred_at),
                kind=event.kind,
                message=event.message,
                evidence=event.evidence or {},
            )
            for event in (events or [])
        ],
    )


async def _routing_out(session: AsyncSession, routing: RoutingState) -> RoutingOut:
    base_url = None
    eligible = False
    if routing.active_environment_id:
        environment = await session.get(Environment, routing.active_environment_id)
        health = await session.get(EnvironmentHealth, routing.active_environment_id)
        base_url = environment.base_url if environment else None
        eligible = bool(health and health.eligible)
    return RoutingOut(
        active_environment_id=routing.active_environment_id,
        mode=routing.mode,
        manual_environment_id=routing.manual_environment_id,
        preferred_environment_id=routing.preferred_environment_id,
        switched_at=_aware(routing.switched_at),
        cooldown_until=_aware(routing.cooldown_until),
        reason=routing.reason,
        generation=routing.generation,
        active_base_url=base_url,
        active_eligible=eligible,
    )


def _experiment_out(row: ExperimentRecord) -> ExperimentOut:
    return ExperimentOut(
        id=row.id,
        kind=row.kind,
        target_environment_id=row.target_environment_id,
        status=row.status,
        requested_by=row.requested_by,
        parameters=row.parameters or {},
        result=row.result,
        started_at=_aware(row.started_at),
        finished_at=_aware(row.finished_at),
    )


async def _routing(session: AsyncSession) -> RoutingState:
    routing = await session.get(RoutingState, 1)
    if routing is None:
        raise HTTPException(status_code=500, detail="Routing state is not initialised.")
    return routing


async def _runtime_settings(session: AsyncSession) -> RuntimeSettings:
    row = await session.get(RuntimeSettings, 1)
    if row is None:
        raise HTTPException(status_code=500, detail="Runtime settings are not initialised.")
    return row


async def _audit(session: AsyncSession, actor: str, action: str, resource: str, detail: dict) -> None:
    session.add(
        AuditEvent(
            occurred_at=datetime.now(timezone.utc),
            actor=actor,
            action=action,
            resource=resource,
            detail=detail,
        )
    )


def _summarise(rows: list[TrafficSample], window_seconds: int, runtime: RuntimeSettings) -> MetricsSummary:
    if not rows:
        return MetricsSummary(
            window_seconds=window_seconds,
            request_count=0,
            error_count=0,
            error_rate=None,
            latency_p50_ms=None,
            latency_p95_ms=None,
            alert_error_rate=runtime.alert_error_rate,
            alert_latency_ms=runtime.alert_latency_ms,
            by_environment=[],
            series=[],
            measurement="No gateway requests were recorded in this window.",
        )
    latencies = [row.latency_ms for row in rows]
    errors = [row for row in rows if row.status_code >= 500 or row.status_code == 0]
    by_env: dict[str, list[TrafficSample]] = defaultdict(list)
    buckets: dict[datetime, list[TrafficSample]] = defaultdict(list)
    for row in rows:
        by_env[row.environment_id].append(row)
        recorded = _aware(row.recorded_at)
        minute = recorded.replace(second=0, microsecond=0)
        buckets[minute].append(row)
    return MetricsSummary(
        window_seconds=window_seconds,
        request_count=len(rows),
        error_count=len(errors),
        error_rate=round(len(errors) / len(rows), 4),
        latency_p50_ms=round(_percentile(latencies, 0.50), 3),
        latency_p95_ms=round(_percentile(latencies, 0.95), 3),
        alert_error_rate=runtime.alert_error_rate,
        alert_latency_ms=runtime.alert_latency_ms,
        by_environment=[
            {
                "environment_id": environment_id,
                "request_count": len(samples),
                "error_count": sum(1 for sample in samples if sample.status_code >= 500 or sample.status_code == 0),
                "latency_p50_ms": round(_percentile([sample.latency_ms for sample in samples], 0.50), 3),
            }
            for environment_id, samples in sorted(by_env.items())
        ],
        series=[
            {
                "minute": minute.isoformat(),
                "request_count": len(samples),
                "error_count": sum(1 for sample in samples if sample.status_code >= 500 or sample.status_code == 0),
                "latency_p50_ms": round(_percentile([sample.latency_ms for sample in samples], 0.50), 3),
            }
            for minute, samples in sorted(buckets.items())
        ],
        measurement="Computed from routing-gateway traffic samples. Health probes are not included.",
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * fraction
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
