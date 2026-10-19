from prometheus_client import CollectorRegistry, Counter, Histogram

registry = CollectorRegistry()

monitor_ticks = Counter(
    "control_plane_monitor_ticks_total",
    "Health monitor iterations.",
    registry=registry,
)
probe_outcomes = Counter(
    "control_plane_probe_outcomes_total",
    "Classified probe outcomes.",
    ["environment", "outcome"],
    registry=registry,
)
route_changes = Counter(
    "control_plane_route_changes_total",
    "Routing changes committed by the control plane.",
    registry=registry,
)
tick_duration = Histogram(
    "control_plane_monitor_tick_seconds",
    "Wall time of one monitor iteration.",
    registry=registry,
)
