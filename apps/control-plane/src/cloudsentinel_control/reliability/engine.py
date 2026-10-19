"""Pure health and routing decisions.

The database and HTTP probes sit outside this module so the rules can be tested
without a cluster, a clock sleep, or a network.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

HARD_FAILURES = frozenset({"network_error", "timeout", "application_error", "readiness_failure"})
OUTCOMES = HARD_FAILURES | {"ok", "latency_degraded"}


@dataclass(frozen=True)
class Thresholds:
    failure_threshold: int
    success_threshold: int
    latency_breach_threshold: int


@dataclass(frozen=True)
class HealthSnapshot:
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    consecutive_latency_breaches: int = 0
    state: str = "unknown"
    circuit: str = "closed"
    eligible: bool = False
    last_outcome: str | None = None


@dataclass(frozen=True)
class RouteSnapshot:
    active_id: str | None
    mode: str
    manual_id: str | None
    cooldown_until: datetime | None
    preferred_id: str
    incident_open: bool


@dataclass(frozen=True)
class DecisionEvent:
    kind: str
    message: str


@dataclass(frozen=True)
class RouteDecision:
    active_id: str | None
    mode: str
    manual_id: str | None
    cooldown_until: datetime | None
    changed: bool
    reason: str
    incident_action: str
    events: tuple[DecisionEvent, ...]


def apply_observation(previous: HealthSnapshot, outcome: str, thresholds: Thresholds) -> HealthSnapshot:
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome: {outcome}")

    failures = previous.consecutive_failures
    successes = previous.consecutive_successes
    latency = previous.consecutive_latency_breaches
    circuit = previous.circuit

    if outcome == "ok":
        failures = 0
        latency = 0
        successes += 1
    elif outcome == "latency_degraded":
        # Latency is a different signal from a hard error. Mixing the counters
        # would let a slow-but-successful service look like a crash, or hide one.
        failures = 0
        successes = 0
        latency += 1
    else:
        successes = 0
        latency = 0
        failures += 1

    if circuit == "half_open" and outcome != "ok":
        circuit = "open"
        successes = 0

    if failures >= thresholds.failure_threshold or latency >= thresholds.latency_breach_threshold:
        circuit = "open"
        successes = 0

    if circuit == "open" and outcome == "ok":
        circuit = "half_open"

    if circuit == "half_open" and outcome == "ok" and successes >= thresholds.success_threshold:
        circuit = "closed"

    if circuit in {"open", "half_open"}:
        eligible = False
    elif successes >= thresholds.success_threshold:
        eligible = True
    else:
        # Stay on the current environment until the threshold is actually crossed.
        eligible = previous.eligible and circuit == "closed"

    if failures >= thresholds.failure_threshold:
        state = "unhealthy"
    elif latency >= thresholds.latency_breach_threshold or circuit == "half_open":
        state = "degraded"
    elif eligible and (failures > 0 or latency > 0):
        state = "degraded"
    elif eligible:
        state = "healthy"
    else:
        state = "unknown"

    return HealthSnapshot(
        consecutive_failures=failures,
        consecutive_successes=successes,
        consecutive_latency_breaches=latency,
        state=state,
        circuit=circuit,
        eligible=eligible,
        last_outcome=outcome,
    )


def select_route(
    now: datetime,
    route: RouteSnapshot,
    health_by_id: dict[str, HealthSnapshot],
    cooldown_seconds: int,
    recovery_policy: str,
) -> RouteDecision:
    def eligible(environment_id: str | None) -> bool:
        if not environment_id:
            return False
        snapshot = health_by_id.get(environment_id)
        return bool(snapshot and snapshot.eligible)

    def decide(
        active_id: str | None,
        mode: str,
        manual_id: str | None,
        cooldown_until: datetime | None,
        reason: str,
        incident_action: str,
        events: tuple[DecisionEvent, ...],
    ) -> RouteDecision:
        changed = active_id != route.active_id or mode != route.mode
        return RouteDecision(
            active_id=active_id,
            mode=mode,
            manual_id=manual_id,
            cooldown_until=cooldown_until,
            changed=changed,
            reason=reason,
            incident_action=incident_action,
            events=events,
        )

    cooling = route.cooldown_until is not None and now < route.cooldown_until

    if route.mode == "manual" and route.manual_id:
        if eligible(route.manual_id):
            cooldown = route.cooldown_until
            events: tuple[DecisionEvent, ...] = ()
            if route.active_id != route.manual_id:
                cooldown = now + timedelta(seconds=cooldown_seconds)
                events = (
                    DecisionEvent("validation", f"{route.manual_id} is eligible for the manual override."),
                    DecisionEvent("routing", f"Manual override moved traffic to {route.manual_id}."),
                )
            return decide(
                route.manual_id,
                "manual",
                route.manual_id,
                cooldown,
                "Manual override is holding traffic on an eligible environment.",
                "none",
                events,
            )
        return decide(
            route.active_id,
            "manual",
            route.manual_id,
            route.cooldown_until,
            "Manual target is not eligible, so traffic stays where it is.",
            "open" if not eligible(route.active_id) else "none",
            (DecisionEvent("validation", f"Manual target {route.manual_id} failed the eligibility check."),),
        )

    preferred = route.preferred_id
    active = route.active_id

    if active is None:
        if eligible(preferred):
            # The first selection is not a failover. Arming the cooldown here would
            # block a real failover if the preferred environment dies immediately.
            return decide(
                preferred,
                "automatic",
                None,
                None,
                "Preferred environment passed the success threshold.",
                "none",
                (DecisionEvent("routing", f"Initial route selected {preferred}."),),
            )
        secondary = _first_eligible(health_by_id, exclude={preferred})
        if secondary:
            # The first selection is not an incident. Nothing has failed yet;
            # the preferred environment simply has not crossed the success threshold.
            return decide(
                secondary,
                "automatic",
                None,
                None,
                "Preferred environment is not eligible yet. The secondary environment is.",
                "none",
                (
                    DecisionEvent("validation", f"{secondary} is eligible."),
                    DecisionEvent("routing", f"Initial route selected {secondary} because {preferred} is not eligible."),
                ),
            )
        return decide(
            None,
            "automatic",
            None,
            route.cooldown_until,
            "No environment is eligible for traffic yet.",
            "none",
            (DecisionEvent("detection", "No eligible environment is available yet."),),
        )

    if eligible(active):
        if active != preferred and eligible(preferred) and recovery_policy == "automatic" and not cooling:
            return decide(
                preferred,
                "automatic",
                None,
                now + timedelta(seconds=cooldown_seconds),
                "Preferred environment recovered and the cooldown has elapsed.",
                "resolve",
                (
                    DecisionEvent("validation", f"{preferred} is eligible again."),
                    DecisionEvent("recovery", f"Traffic returned to preferred environment {preferred}."),
                    DecisionEvent("resolution", "Incident closed after the preferred environment recovered."),
                ),
            )
        reason = "Active environment remains eligible."
        events = ()
        action = "none"
        if cooling and active != preferred and eligible(preferred):
            reason = "Preferred environment is eligible, but the cooldown is still running."
            events = (DecisionEvent("recovery", reason),)
        elif route.incident_open and active == preferred:
            action = "resolve"
            events = (DecisionEvent("resolution", "Preferred environment is eligible again. Incident closed."),)
        return decide(active, "automatic", None, route.cooldown_until, reason, action, events)

    if cooling:
        return decide(
            active,
            "automatic",
            None,
            route.cooldown_until,
            "Active environment is unhealthy, but the cooldown blocks another switch.",
            "open",
            (DecisionEvent("detection", "Failover is suppressed because the cooldown has not elapsed."),),
        )

    if eligible(preferred) and preferred != active:
        destination = preferred
    else:
        destination = _first_eligible(health_by_id, exclude={active})

    if destination is None:
        return decide(
            active,
            "automatic",
            None,
            route.cooldown_until,
            "Active environment is unhealthy and no other environment is eligible.",
            "open",
            (
                DecisionEvent("detection", f"{active} crossed the failure threshold."),
                DecisionEvent("validation", "No destination passed the eligibility check. Traffic was not moved."),
            ),
        )

    return decide(
        destination,
        "automatic",
        None,
        now + timedelta(seconds=cooldown_seconds),
        "Destination verified healthy. New requests will use it.",
        "open",
        (
            DecisionEvent("detection", f"{active} is no longer eligible."),
            DecisionEvent("validation", f"{destination} is eligible and can accept requests."),
            DecisionEvent("routing", f"Traffic moved from {active} to {destination}."),
        ),
    )


def _first_eligible(health_by_id: dict[str, HealthSnapshot], exclude: set[str]) -> str | None:
    for environment_id in sorted(health_by_id):
        if environment_id in exclude:
            continue
        if health_by_id[environment_id].eligible:
            return environment_id
    return None
