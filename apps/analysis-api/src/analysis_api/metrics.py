from prometheus_client import CollectorRegistry, Counter, Histogram

registry = CollectorRegistry()

requests_total = Counter(
    "analysis_http_requests_total",
    "HTTP requests handled by the analysis API.",
    ["method", "path", "status"],
    registry=registry,
)
analysis_duration = Histogram(
    "analysis_processing_seconds",
    "Time spent inside the analysis backend.",
    ["backend"],
    registry=registry,
)
faults_active = Counter(
    "analysis_faults_applied_total",
    "Fault-injection updates accepted by this process.",
    ["mode"],
    registry=registry,
)
