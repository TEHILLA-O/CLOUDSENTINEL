import asyncio
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from analysis_api import __version__
from analysis_api.analyser import analyse_text
from analysis_api.config import Settings, get_settings
from analysis_api.faults import FaultController
from analysis_api.llm import analyse_with_llm
from analysis_api.logging import configure_logging
from analysis_api.metrics import analysis_duration, faults_active, registry, requests_total
from analysis_api.schemas import (
    AnalyseRequest,
    AnalyseResponse,
    ErrorResponse,
    FaultRequest,
    FaultResponse,
    HealthResponse,
    KeywordModel,
    SentimentModel,
    StatisticsModel,
    VersionResponse,
)

logger = logging.getLogger("analysis_api")


class RequestContextMiddleware:
    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        header_map = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
        request_id = header_map.get("x-request-id") or str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        content_length = header_map.get("content-length", "")
        if content_length.isdigit() and int(content_length) > self.settings.max_body_bytes:
            body = _error(413, "payload_too_large", "Request body exceeds the configured limit.", request_id).body
            await _send_raw(send, 413, body, request_id, 0)
            return
        started = time.perf_counter()
        status_holder = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                elapsed = f"{(time.perf_counter() - started) * 1000:.1f}"
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-process-time-ms", elapsed.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("unhandled error", extra={"request_id": request_id})
            body = _error(
                500,
                "internal_error",
                "The analysis service failed while handling the request.",
                request_id,
            ).body
            elapsed = (time.perf_counter() - started) * 1000
            await _send_raw(send, 500, body, request_id, elapsed)
            status_holder["code"] = 500
        finally:
            path = scope.get("path", "")
            if path.startswith("/api/v1/analyse"):
                metric_path = "/api/v1/analyse"
            elif path.startswith("/health") or path.startswith("/internal"):
                metric_path = path
            else:
                metric_path = path
            requests_total.labels(scope.get("method", "GET"), metric_path, str(status_holder["code"])).inc()


async def _send_raw(send, status: int, body: bytes, request_id: str, elapsed_ms: float) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-request-id", request_id.encode()),
                (b"x-content-type-options", b"nosniff"),
                (b"x-process-time-ms", f"{elapsed_ms:.1f}".encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.analysis_backend == "openai" and not settings.openai_api_key:
            logger.warning("ANALYSIS_BACKEND=openai but OPENAI_API_KEY is empty; analyse will return 503.")
        if settings.fault_injection_enabled and not settings.fault_token:
            logger.warning("Fault injection is enabled without FAULT_TOKEN; the endpoint will reject every call.")
        yield

    app = FastAPI(
        title="CloudSentinel Analysis API",
        version=__version__,
        summary="Document and text analysis API.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.faults = FaultController()

    # Raw ASGI middleware, not BaseHTTPMiddleware. The Starlette base class can
    # deadlock when a synchronous endpoint raises, which is exactly how faults
    # and validation failures are reported.
    app.add_middleware(RequestContextMiddleware, settings=settings)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        details = []
        for item in exc.errors():
            details.append({"loc": [str(part) for part in item.get("loc", [])], "msg": item.get("msg", "invalid")})
        return _error(
            422,
            "validation_error",
            "The request body did not match the analysis schema.",
            _request_id(request),
            details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            413: "payload_too_large",
            503: "unavailable",
        }.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, message, _request_id(request))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        # Log the type server-side. The client gets a stable message and no traceback.
        logger.exception("unhandled error", extra={"request_id": _request_id(request)})
        return _error(500, "internal_error", "The analysis service failed while handling the request.", _request_id(request))

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    def live() -> HealthResponse:
        fault = app.state.faults.current()
        if fault.mode == "unliveness":
            raise StarletteHTTPException(status_code=503, detail="Liveness fault is active.")
        return HealthResponse(status="alive", environment=settings.environment_name)

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    def ready() -> HealthResponse:
        fault = app.state.faults.current()
        if fault.mode == "unreadiness":
            raise StarletteHTTPException(status_code=503, detail="Readiness fault is active.")
        if fault.mode == "unliveness":
            raise StarletteHTTPException(status_code=503, detail="Process is marked not alive.")
        if fault.mode == "latency" and fault.latency_ms:
            # Sync sleep is deliberate: this is the fault, and it should occupy a worker
            # the same way a stuck handler would. Kubernetes still has /health/live.
            time.sleep(fault.latency_ms / 1000)
        return HealthResponse(status="ready", environment=settings.environment_name)

    @app.get("/api/v1/version", response_model=VersionResponse, tags=["analysis"])
    def version() -> VersionResponse:
        return VersionResponse(
            name="analysis-api",
            version=settings.app_version,
            environment=settings.environment_name,
            provider=settings.environment_provider,
            backend=settings.analysis_backend,
        )

    @app.post(
        "/api/v1/analyse",
        response_model=AnalyseResponse,
        responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        tags=["analysis"],
    )
    async def analyse(body: AnalyseRequest, request: Request) -> AnalyseResponse:
        fault = app.state.faults.current()
        if fault.mode == "latency" and fault.latency_ms:
            await asyncio.sleep(fault.latency_ms / 1000)
        if fault.mode == "errors":
            raise StarletteHTTPException(status_code=fault.error_status, detail="Injected analysis failure.")
        if fault.mode == "unliveness":
            raise StarletteHTTPException(status_code=503, detail="Analysis process is marked not alive.")

        request_id = request.state.request_id
        if settings.analysis_backend == "deterministic":
            # The lexicon scan is CPU work. It is tiny at the 32KB cap, but it does not
            # belong on the event loop if a caller raises the cap later.
            result = await asyncio.to_thread(
                analyse_text,
                body.text,
                body.language,
                body.options.max_keywords if body.options.include_keywords else 0,
            )
            backend = "deterministic"
        elif settings.analysis_backend == "openai":
            if not settings.openai_api_key:
                raise StarletteHTTPException(status_code=503, detail="The LLM backend is not configured.")
            try:
                result = await analyse_with_llm(body.text, body.language, settings)
            except Exception:
                logger.exception("llm backend failed", extra={"request_id": request_id})
                raise StarletteHTTPException(status_code=502, detail="The LLM backend did not return a usable analysis.") from None
            backend = "openai"
        else:
            raise StarletteHTTPException(status_code=500, detail="Unknown analysis backend.")

        analysis_duration.labels(backend).observe(result.processing_ms / 1000)
        keywords = [KeywordModel(term=item.term, score=item.score) for item in result.keywords] if body.options.include_keywords else []
        return AnalyseResponse(
            request_id=request_id,
            summary=result.summary,
            language=body.language,
            sentiment=SentimentModel(label=result.sentiment_label, score=result.sentiment_score, note=result.sentiment_note),
            keywords=keywords,
            statistics=StatisticsModel(
                characters=result.characters,
                words=result.words,
                sentences=result.sentences,
                reading_time_seconds=result.reading_time_seconds,
            ),
            backend=backend,
            processing_ms=result.processing_ms,
            environment=settings.environment_name,
            provider=settings.environment_provider,
        )

    @app.post("/internal/faults", response_model=FaultResponse, tags=["internal"])
    def set_fault(body: FaultRequest, request: Request) -> FaultResponse:
        if not settings.fault_injection_enabled:
            raise StarletteHTTPException(status_code=404, detail="Not found.")
        supplied = request.headers.get("x-fault-token", "")
        if not settings.fault_token or not secrets.compare_digest(supplied, settings.fault_token):
            raise StarletteHTTPException(status_code=401, detail="Fault token was rejected.")
        applied = app.state.faults.apply(body.mode, body.latency_ms, body.error_status, body.duration_seconds)
        faults_active.labels(applied.mode).inc()
        logger.info("fault updated mode=%s duration=%s", applied.mode, body.duration_seconds)
        return FaultResponse(
            mode=applied.mode,
            latency_ms=applied.latency_ms,
            error_status=applied.error_status,
            expires_at=applied.expires_at.isoformat() if applied.expires_at else None,
        )

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return app


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("x-request-id") or "unknown"


def _error(status: int, error: str, message: str, request_id: str, details: list[dict] | None = None) -> JSONResponse:
    body = ErrorResponse(error=error, message=message, request_id=request_id, details=details).model_dump()
    return JSONResponse(status_code=status, content=body)


app = create_app()
