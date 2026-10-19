import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudsentinel_control.metrics import monitor_ticks, probe_outcomes, route_changes, tick_duration
from cloudsentinel_control.models import (
    Environment,
    EnvironmentHealth,
    HealthObservation,
    Incident,
    IncidentEvent,
    RoutingState,
    RuntimeSettings,
    Service,
    TrafficSample,
)
from cloudsentinel_control.reliability.engine import (
    HARD_FAILURES,
    HealthSnapshot,
    RouteSnapshot,
    Thresholds,
    apply_observation,
    select_route,
)
from cloudsentinel_control.reliability.probe import PROBE_TEXT, classify, fetch

logger = logging.getLogger("cloudsentinel.monitor")


async def run_monitor_tick(session: AsyncSession, client: httpx.AsyncClient, probe_timeout: float) -> int:
    """Probe every enabled environment once and apply at most one routing change.

    Returns the configured interval so the caller can sleep. The interval is
    read from the database, which is what the settings page writes.
    """
    started = time.perf_counter()
    settings = await _settings(session)
    environments = list(await session.scalars(select(Environment).where(Environment.enabled.is_(True))))
    health_rows = {row.environment_id: row for row in await session.scalars(select(EnvironmentHealth))}
    services = {row.environment_id: row for row in await session.scalars(select(Service))}
    thresholds = Thresholds(
        failure_threshold=settings.failure_threshold,
        success_threshold=settings.success_threshold,
        latency_breach_threshold=settings.latency_breach_threshold,
    )
    now = datetime.now(timezone.utc)
    snapshots: dict[str, HealthSnapshot] = {}

    for environment in environments:
        health = health_rows[environment.id]
        outcome, latency_ms, status_code, detail = await _probe(
            client, environment.base_url, probe_timeout, settings.latency_threshold_ms
        )
        previous = _snapshot(health)
        updated = apply_observation(previous, outcome, thresholds)
        _write_health(health, updated, outcome, latency_ms, status_code, detail, now, previous)
        service = services.get(environment.id)
        session.add(
            HealthObservation(
                environment_id=environment.id,
                service_id=service.id if service else environment.id,
                checked_at=now,
                outcome=outcome,
                latency_ms=latency_ms,
                status_code=status_code,
                detail=detail,
            )
        )
        snapshots[environment.id] = updated
        probe_outcomes.labels(environment.id, outcome).inc()

    routing = await session.get(RoutingState, 1)
    if routing is None or not snapshots:
        return settings.health_check_interval_seconds

    open_incident = await session.scalar(select(Incident).where(Incident.status == "open"))
    decision = select_route(
        now,
        RouteSnapshot(
            active_id=routing.active_environment_id,
            mode=routing.mode,
            manual_id=routing.manual_environment_id,
            cooldown_until=_aware(routing.cooldown_until),
            preferred_id=settings.preferred_environment_id or routing.preferred_environment_id or "",
            incident_open=open_incident is not None,
        ),
        snapshots,
        settings.cooldown_seconds,
        settings.recovery_policy,
    )

    previous_active = routing.active_environment_id
    previous_reason = routing.reason
    if decision.changed or decision.reason != routing.reason:
        routing.reason = decision.reason
    if decision.changed:
        routing.active_environment_id = decision.active_id
        routing.mode = decision.mode
        routing.switched_at = now
        routing.cooldown_until = decision.cooldown_until
        routing.generation += 1
        route_changes.inc()
        logger.info(
            "route changed from %s to %s generation=%s",
            previous_active,
            decision.active_id,
            routing.generation,
        )
    elif decision.cooldown_until != routing.cooldown_until:
        routing.cooldown_until = decision.cooldown_until

    record_events = decision.changed or decision.reason != previous_reason or decision.incident_action == "resolve"
    incident = await _apply_incident(
        session,
        decision.incident_action,
        decision.events if record_events else (),
        open_incident,
        routing,
        settings,
        health_rows,
        now,
        decision.changed,
        previous_active,
    )
    cutoff = now - timedelta(days=2)
    await session.execute(delete(HealthObservation).where(HealthObservation.checked_at < cutoff))
    await session.execute(delete(TrafficSample).where(TrafficSample.recorded_at < cutoff))
    monitor_ticks.inc()
    tick_duration.observe(time.perf_counter() - started)
    return settings.health_check_interval_seconds


async def _probe(client: httpx.AsyncClient, base_url: str, timeout: float, latency_threshold_ms: float):
    root = base_url.rstrip("/")
    live = await fetch(client, "GET", f"{root}/health/live", timeout)
    if live.error or live.status != 200:
        return classify(live, None, None, latency_threshold_ms)
    ready = await fetch(client, "GET", f"{root}/health/ready", timeout)
    if ready.error or ready.status != 200:
        return classify(live, ready, None, latency_threshold_ms)
    application = await fetch(
        client,
        "POST",
        f"{root}/api/v1/analyse",
        timeout,
        {"text": PROBE_TEXT, "language": "en"},
    )
    return classify(live, ready, application, latency_threshold_ms)


def _snapshot(health: EnvironmentHealth) -> HealthSnapshot:
    return HealthSnapshot(
        consecutive_failures=health.consecutive_failures,
        consecutive_successes=health.consecutive_successes,
        consecutive_latency_breaches=health.consecutive_latency_breaches,
        state=health.state,
        circuit=health.circuit,
        eligible=health.eligible,
        last_outcome=health.last_outcome,
    )


def _write_health(
    health: EnvironmentHealth,
    updated: HealthSnapshot,
    outcome: str,
    latency_ms: float,
    status_code: int | None,
    detail: str,
    now: datetime,
    previous: HealthSnapshot,
) -> None:
    starting_failure = outcome in HARD_FAILURES | {"latency_degraded"} and (
        (outcome in HARD_FAILURES and previous.consecutive_failures == 0)
        or (outcome == "latency_degraded" and previous.consecutive_latency_breaches == 0)
    )
    if starting_failure and health.failure_window_started_at is None:
        health.failure_window_started_at = now
    if outcome == "ok" and updated.eligible and updated.consecutive_failures == 0 and updated.consecutive_latency_breaches == 0:
        health.failure_window_started_at = None
    health.consecutive_failures = updated.consecutive_failures
    health.consecutive_successes = updated.consecutive_successes
    health.consecutive_latency_breaches = updated.consecutive_latency_breaches
    health.state = updated.state
    health.circuit = updated.circuit
    health.eligible = updated.eligible
    health.last_outcome = outcome
    health.last_detail = detail
    health.last_latency_ms = latency_ms
    health.last_status_code = status_code
    health.last_checked_at = now


async def _apply_incident(
    session: AsyncSession,
    action: str,
    events,
    open_incident: Incident | None,
    routing: RoutingState,
    settings: RuntimeSettings,
    health_rows: dict[str, EnvironmentHealth],
    now: datetime,
    route_changed: bool,
    previous_active: str | None,
) -> Incident | None:
    if action == "none" and not events:
        return open_incident
    incident = open_incident
    if incident is None and action == "open":
        failed = previous_active if previous_active in health_rows else None
        failed_health = health_rows.get(failed) if failed else None
        incident = Incident(
            id=str(uuid.uuid4()),
            status="open",
            summary=routing.reason,
            trigger=failed_health.last_outcome if failed_health and failed_health.last_outcome else "unknown",
            started_at=now,
            detected_at=now,
            failure_window_started_at=failed_health.failure_window_started_at if failed_health else None,
            preferred_environment_id=settings.preferred_environment_id,
            from_environment_id=previous_active,
            to_environment_id=routing.active_environment_id if route_changed else None,
        )
        session.add(incident)
        await session.flush()
    if incident is not None and (events or action == "resolve"):
        incident.summary = routing.reason
        for event in events:
            session.add(
                IncidentEvent(
                    incident_id=incident.id,
                    occurred_at=now,
                    kind=event.kind,
                    message=event.message,
                    evidence={
                        "active_environment_id": routing.active_environment_id,
                        "previous_environment_id": previous_active,
                        "route_changed": route_changed,
                        "generation": routing.generation,
                    },
                )
            )
        if route_changed and routing.active_environment_id and incident.routing_changed_at is None:
            incident.routing_changed_at = now
            incident.to_environment_id = routing.active_environment_id
        if action == "resolve" and incident.status == "open":
            incident.status = "resolved"
            incident.resolved_at = now
    return incident


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _settings(session: AsyncSession) -> RuntimeSettings:
    settings = await session.get(RuntimeSettings, 1)
    if settings is None:
        raise RuntimeError("runtime settings were not seeded")
    return settings
