import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from cloudsentinel_control import __version__
from cloudsentinel_control.config import Settings, get_settings
from cloudsentinel_control.db import create_engine, init_database, session_factory
from cloudsentinel_control.logging import configure_logging
from cloudsentinel_control.metrics import registry
from cloudsentinel_control.reliability.monitor import run_monitor_tick
from cloudsentinel_control.routers.http import bind
from cloudsentinel_control.schemas import ErrorBody
from cloudsentinel_control.seed import apply_environment_config, seed_if_empty

logger = logging.getLogger("cloudsentinel.control")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(settings.database_url)
        factory = session_factory(engine)
        await init_database(engine)
        async with factory() as session:
            await seed_if_empty(session, settings)
            await apply_environment_config(session, settings)
            await session.commit()
        app.state.engine = engine
        app.state.session_factory = factory
        app.state.http = httpx.AsyncClient()
        stop = asyncio.Event()

        async def loop():
            while not stop.is_set():
                interval = 5
                try:
                    async with factory() as session:
                        interval = await run_monitor_tick(session, app.state.http, settings.probe_timeout_seconds)
                        await session.commit()
                except Exception:
                    logger.exception("monitor tick failed")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval)
                except TimeoutError:
                    continue

        task = asyncio.create_task(loop()) if settings.monitor_enabled else None
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await app.state.http.aclose()
            await engine.dispose()

    app = FastAPI(
        title="CloudSentinel Control Plane",
        version=__version__,
        summary="Health monitoring, incident history, and routing decisions.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        details = [{"loc": [str(part) for part in item.get("loc", [])], "msg": item.get("msg", "invalid")} for item in exc.errors()]
        return _error(422, "validation_error", "The request did not match the API schema.", _request_id(request), details)

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict", 422: "validation_error"}.get(
            exc.status_code, "http_error"
        )
        return _error(exc.status_code, code, message, _request_id(request))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error", extra={"request_id": _request_id(request)})
        return _error(500, "internal_error", "The control plane failed while handling the request.", _request_id(request))

    app.include_router(bind(settings))

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return app


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "unknown"


def _error(status: int, error: str, message: str, request_id: str, details: list[dict] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=ErrorBody(error=error, message=message, request_id=request_id, details=details).model_dump())


app = create_app()
