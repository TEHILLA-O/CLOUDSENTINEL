from datetime import datetime, timedelta, timezone

import pytest

from cloudsentinel_control.reliability.engine import (
    HealthSnapshot,
    RouteSnapshot,
    Thresholds,
    apply_observation,
    select_route,
)
from cloudsentinel_control.reliability.probe import Attempt, classify

THRESHOLDS = Thresholds(failure_threshold=3, success_threshold=2, latency_breach_threshold=3)
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def _drive(outcomes: list[str], start: HealthSnapshot | None = None) -> HealthSnapshot:
    health = start or HealthSnapshot()
    for outcome in outcomes:
        health = apply_observation(health, outcome, THRESHOLDS)
    return health


def test_two_successes_are_required_before_an_environment_is_eligible():
    once = _drive(["ok"])
    assert once.eligible is False
    assert once.state == "unknown"
    twice = _drive(["ok", "ok"])
    assert twice.eligible is True
    assert twice.state == "healthy"
    assert twice.circuit == "closed"


def test_one_failure_does_not_remove_an_eligible_environment():
    health = _drive(["ok", "ok", "application_error"])
    assert health.eligible is True
    assert health.state == "degraded"
    assert health.consecutive_failures == 1
    assert health.circuit == "closed"


def test_failure_threshold_opens_the_circuit():
    health = _drive(["ok", "ok", "timeout", "network_error", "application_error"])
    assert health.eligible is False
    assert health.state == "unhealthy"
    assert health.circuit == "open"
    assert health.consecutive_failures == 3


def test_intermittent_failures_do_not_open_the_circuit():
    health = _drive(["ok", "ok", "timeout", "ok", "network_error", "ok", "readiness_failure"])
    assert health.eligible is True
    assert health.circuit == "closed"
    assert health.consecutive_failures == 1


def test_latency_uses_its_own_threshold():
    health = _drive(["ok", "ok", "latency_degraded", "latency_degraded"])
    assert health.eligible is True
    assert health.state == "degraded"
    assert health.consecutive_failures == 0
    opened = apply_observation(health, "latency_degraded", THRESHOLDS)
    assert opened.eligible is False
    assert opened.state == "degraded"
    assert opened.circuit == "open"


def test_half_open_failure_reopens_and_successes_close():
    opened = _drive(["ok", "ok", "timeout", "timeout", "timeout"])
    half = apply_observation(opened, "ok", THRESHOLDS)
    assert half.circuit == "half_open"
    assert half.eligible is False
    reopened = apply_observation(half, "timeout", THRESHOLDS)
    assert reopened.circuit == "open"
    assert reopened.eligible is False
    recovered = _drive(["ok", "ok"], start=opened)
    assert recovered.circuit == "closed"
    assert recovered.eligible is True
    assert recovered.state == "healthy"


def test_unknown_outcome_is_rejected():
    with pytest.raises(ValueError):
        apply_observation(HealthSnapshot(), "maybe", THRESHOLDS)


def _route(active: str | None, health: dict[str, HealthSnapshot], **kwargs) -> object:
    snapshot = RouteSnapshot(
        active_id=active,
        mode=kwargs.get("mode", "automatic"),
        manual_id=kwargs.get("manual_id"),
        cooldown_until=kwargs.get("cooldown_until"),
        preferred_id=kwargs.get("preferred_id", "azure-dev"),
        incident_open=kwargs.get("incident_open", False),
    )
    return select_route(NOW, snapshot, health, cooldown_seconds=30, recovery_policy=kwargs.get("recovery_policy", "automatic"))


def test_initial_route_waits_for_the_preferred_environment():
    health = {
        "azure-dev": _drive(["ok", "ok"]),
        "gcp-dev": _drive(["ok", "ok"]),
    }
    decision = _route(None, health)
    assert decision.active_id == "azure-dev"
    assert decision.changed is True
    assert decision.incident_action == "none"


def test_failover_requires_an_eligible_destination():
    azure = _drive(["ok", "ok", "timeout", "timeout", "timeout"])
    gcp = _drive(["ok", "ok"])
    decision = _route("azure-dev", {"azure-dev": azure, "gcp-dev": gcp})
    assert decision.active_id == "gcp-dev"
    assert decision.changed is True
    assert decision.incident_action == "open"
    assert {event.kind for event in decision.events} >= {"detection", "validation", "routing"}


def test_failover_does_not_move_when_the_secondary_is_unhealthy():
    azure = _drive(["ok", "ok", "timeout", "timeout", "timeout"])
    gcp = _drive(["timeout", "timeout", "timeout"])
    decision = _route("azure-dev", {"azure-dev": azure, "gcp-dev": gcp})
    assert decision.active_id == "azure-dev"
    assert decision.changed is False
    assert decision.incident_action == "open"
    assert any(event.kind == "validation" for event in decision.events)


def test_cooldown_blocks_a_second_switch():
    azure = _drive(["ok", "ok"])
    gcp = _drive(["timeout", "timeout", "timeout"])
    decision = _route(
        "gcp-dev",
        {"azure-dev": azure, "gcp-dev": gcp},
        cooldown_until=NOW + timedelta(seconds=10),
    )
    assert decision.active_id == "gcp-dev"
    assert decision.changed is False
    assert "cooldown" in decision.reason.lower()


def test_automatic_recovery_returns_to_the_preferred_environment():
    decision = _route(
        "gcp-dev",
        {"azure-dev": _drive(["ok", "ok"]), "gcp-dev": _drive(["ok", "ok"])},
        incident_open=True,
    )
    assert decision.active_id == "azure-dev"
    assert decision.incident_action == "resolve"
    assert any(event.kind == "recovery" for event in decision.events)


def test_manual_recovery_policy_does_not_switch_back():
    decision = _route(
        "gcp-dev",
        {"azure-dev": _drive(["ok", "ok"]), "gcp-dev": _drive(["ok", "ok"])},
        recovery_policy="manual",
        incident_open=True,
    )
    assert decision.active_id == "gcp-dev"
    assert decision.changed is False


def test_manual_override_refuses_an_ineligible_target_inside_the_engine():
    decision = _route(
        "azure-dev",
        {"azure-dev": _drive(["ok", "ok"]), "gcp-dev": HealthSnapshot()},
        mode="manual",
        manual_id="gcp-dev",
    )
    assert decision.active_id == "azure-dev"
    assert decision.changed is False
    assert any(event.kind == "validation" for event in decision.events)


def test_probe_classification_distinguishes_failure_modes():
    ok = Attempt(None, 200, 20)
    assert classify(ok, ok, Attempt(None, 200, 30), 800)[0] == "ok"
    assert classify(Attempt("network", None, 5), None, None, 800)[0] == "network_error"
    assert classify(Attempt("timeout", None, 2000), None, None, 800)[0] == "timeout"
    assert classify(Attempt(None, 500, 10), None, None, 800)[0] == "application_error"
    assert classify(ok, Attempt(None, 503, 15), None, 800)[0] == "readiness_failure"
    assert classify(ok, ok, Attempt(None, 500, 40), 800)[0] == "application_error"
    assert classify(ok, ok, Attempt(None, 200, 1500), 800)[0] == "latency_degraded"
    assert classify(ok, ok, Attempt("timeout", None, 2000), 800)[0] == "timeout"
