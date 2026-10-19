import logging
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

from cloudsentinel_gateway import __version__
from cloudsentinel_gateway.config import Settings, get_settings

logger = logging.getLogger("cloudsentinel.gateway")

# Closed set. The gateway is not an open proxy.
PROXIED = {
    ("POST", "/api/v1/analyse"),
    ("GET", "/api/v1/version"),
}

registry = CollectorRegistry()
proxied_requests = Counter(
    "gateway_proxied_requests_total",
    "Requests forwarded by the gateway.",
    ["environment", "status"],
    registry=registry,
)
proxy_latency = Histogram(
    "gateway_upstream_seconds",
    "Time spent waiting for the selected analysis service.",
    registry=registry,
)


class RouteCache:
    def __init__(self) -> None:
        self.environment_id: str | None = None
        self.base_url: str | None = None
        self.fetched_at: float = 0.0

    def fresh(self, ttl: float) -> bool:
        return self.base_url is not None and (time.monotonic() - self.fetched_at) <= ttl

    def usable(self, stale_ttl: float) -> bool:
        return self.base_url is not None and (time.monotonic() - self.fetched_at) <= stale_ttl


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http = httpx.AsyncClient()
        app.state.routes = RouteCache()
        try:
            yield
        finally:
            await app.state.http.aclose()

    app = FastAPI(
        title="CloudSentinel Routing Gateway",
        version=__version__,
        summary="Forwards analysis requests to the environment selected by the control plane.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health/live", tags=["health"])
    async def live():
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"])
    async def ready():
        # Ready means this process can accept work. It does not mean an upstream is healthy.
        # That distinction belongs to the control plane, otherwise a failover target
        # being down would mark the gateway itself down and hide the real failure.
        return {"status": "ready", "data_plane": "reverse-proxy", "dns_failover": False}

    @app.api_route("/api/v1/analyse", methods=["POST"], tags=["proxy"])
    @app.api_route("/api/v1/version", methods=["GET"], tags=["proxy"])
    async def proxy(request: Request):
        if (request.method, request.url.path) not in PROXIED:
            return _error(404, "not_found", "This path is not proxied.", request.state.request_id)
        route = await _resolve_route(app, settings)
        if route is None:
            return _error(
                503,
                "no_route",
                "No eligible environment is available, or the control plane could not be reached.",
                request.state.request_id,
            )
        environment_id, base_url = route
        body = await request.body()
        headers = {"X-Request-ID": request.state.request_id}
        content_type = request.headers.get("content-type")
        if content_type:
            headers["Content-Type"] = content_type
        started = time.perf_counter()
        try:
            upstream = await app.state.http.request(
                request.method,
                f"{base_url.rstrip('/')}{request.url.path}",
                content=body,
                headers=headers,
                timeout=settings.upstream_timeout_seconds,
            )
        except httpx.TimeoutException:
            elapsed_ms = (time.perf_counter() - started) * 1000
            await _report(app, settings, request.state.request_id, environment_id, 0, elapsed_ms, request.url.path, "timeout")
            proxied_requests.labels(environment_id, "0").inc()
            return _error(504, "upstream_timeout", "The selected analysis service timed out.", request.state.request_id)
        except httpx.HTTPError:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception("upstream connection failed")
            await _report(app, settings, request.state.request_id, environment_id, 0, elapsed_ms, request.url.path, "network")
            proxied_requests.labels(environment_id, "0").inc()
            return _error(502, "upstream_unreachable", "The selected analysis service could not be reached.", request.state.request_id)

        elapsed_ms = (time.perf_counter() - started) * 1000
        proxy_latency.observe(elapsed_ms / 1000)
        proxied_requests.labels(environment_id, str(upstream.status_code)).inc()
        await _report(
            app,
            settings,
            request.state.request_id,
            environment_id,
            upstream.status_code,
            elapsed_ms,
            request.url.path,
            None if upstream.status_code < 500 else "upstream_error",
        )
        response_headers = {
            "X-CloudSentinel-Environment": environment_id,
            "X-Request-ID": request.state.request_id,
        }
        content_type = upstream.headers.get("content-type")
        if content_type:
            response_headers["Content-Type"] = content_type
        return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return app


async def _resolve_route(app: FastAPI, settings: Settings) -> tuple[str, str] | None:
    cache: RouteCache = app.state.routes
    if cache.fresh(settings.route_cache_ttl_seconds):
        return cache.environment_id, cache.base_url  # type: ignore[return-value]
    try:
        response = await app.state.http.get(
            f"{settings.control_plane_url.rstrip('/')}/api/v1/routing/current",
            headers={"Authorization": f"Bearer {settings.gateway_token}"},
            timeout=2.0,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError:
        logger.warning("control plane route lookup failed; considering the cached decision")
        if cache.usable(settings.route_stale_ttl_seconds) and cache.environment_id and cache.base_url:
            return cache.environment_id, cache.base_url
        return None
    environment_id = payload.get("active_environment_id")
    base_url = payload.get("active_base_url")
    if not environment_id or not base_url or not payload.get("active_eligible"):
        # A definite "nothing is eligible" must not keep sending traffic to a stale target.
        cache.environment_id = None
        cache.base_url = None
        cache.fetched_at = time.monotonic()
        return None
    cache.environment_id = environment_id
    cache.base_url = base_url
    cache.fetched_at = time.monotonic()
    return environment_id, base_url


async def _report(app, settings, request_id, environment_id, status_code, latency_ms, path, error):
    try:
        await app.state.http.post(
            f"{settings.control_plane_url.rstrip('/')}/internal/traffic",
            headers={"Authorization": f"Bearer {settings.gateway_token}"},
            json={
                "request_id": request_id,
                "environment_id": environment_id,
                "status_code": status_code,
                "latency_ms": round(latency_ms, 3),
                "path": path,
                "error": error,
            },
            timeout=1.0,
        )
    except httpx.HTTPError:
        logger.warning("failed to record traffic sample request_id=%s", request_id)


def _error(status: int, error: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message, "request_id": request_id})


app = create_app()
