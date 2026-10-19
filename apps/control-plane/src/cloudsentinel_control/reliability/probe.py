import time
from dataclasses import dataclass

import httpx

PROBE_TEXT = "cloudsentinel health probe"


@dataclass(frozen=True)
class Attempt:
    error: str | None
    status: int | None
    latency_ms: float


async def fetch(client: httpx.AsyncClient, method: str, url: str, timeout: float, json_body: dict | None = None) -> Attempt:
    started = time.perf_counter()
    try:
        response = await client.request(method, url, timeout=timeout, json=json_body)
    except httpx.TimeoutException:
        return Attempt("timeout", None, _elapsed(started))
    except httpx.HTTPError:
        return Attempt("network", None, _elapsed(started))
    return Attempt(None, response.status_code, _elapsed(started))


def classify(
    live: Attempt,
    ready: Attempt | None,
    application: Attempt | None,
    latency_threshold_ms: float,
) -> tuple[str, float, int | None, str]:
    """Collapse three probes into one outcome.

    Live is checked first because a dead process makes readiness and analysis
    uninteresting. Readiness is next. The analysis call is what users hit, so
    its status and latency decide application health once the process is up.
    """
    if live.error == "network":
        return "network_error", live.latency_ms, None, "Live probe could not connect."
    if live.error == "timeout":
        return "timeout", live.latency_ms, None, "Live probe timed out."
    if live.status != 200:
        return "application_error", live.latency_ms, live.status, f"Live probe returned HTTP {live.status}."

    if ready is None or ready.error == "network":
        return "network_error", (ready.latency_ms if ready else live.latency_ms), None, "Readiness probe could not connect."
    if ready.error == "timeout":
        return "timeout", ready.latency_ms, None, "Readiness probe timed out."
    if ready.status != 200:
        return "readiness_failure", ready.latency_ms, ready.status, f"Readiness probe returned HTTP {ready.status}."

    if application is None or application.error == "network":
        latency = application.latency_ms if application else ready.latency_ms
        return "network_error", latency, None, "Analysis probe could not connect."
    if application.error == "timeout":
        return "timeout", application.latency_ms, None, "Analysis probe timed out."
    if application.status != 200:
        return (
            "application_error",
            application.latency_ms,
            application.status,
            f"Analysis probe returned HTTP {application.status}.",
        )
    if application.latency_ms > latency_threshold_ms:
        return (
            "latency_degraded",
            application.latency_ms,
            application.status,
            f"Analysis latency {application.latency_ms:.0f}ms crossed {latency_threshold_ms:.0f}ms.",
        )
    return "ok", application.latency_ms, application.status, "Live, ready, and analysis probes succeeded."


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
