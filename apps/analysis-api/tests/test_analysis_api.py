import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from analysis_api.analyser import analyse_text
from analysis_api.config import Settings
from analysis_api.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment_name="azure-dev",
        environment_provider="azure",
        analysis_backend="deterministic",
        fault_injection_enabled=True,
        fault_token="test-fault-token",
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://analysis") as http:
        yield http


def test_deterministic_analysis_is_stable():
    text = "The reliable cluster recovered after the failure. The reliable cluster stayed healthy."
    first = analyse_text(text, "en", 5)
    second = analyse_text(text, "en", 5)
    assert first.summary == second.summary
    assert first.sentiment_label == "positive"
    assert first.keywords[0].term == "cluster"
    assert first.processing_ms >= 0


def test_non_english_skips_sentiment_lexicon():
    result = analyse_text("El servicio fallo.", "es", 5)
    assert result.sentiment_label is None
    assert result.sentiment_note
    assert result.words >= 2


async def test_analyse_endpoint_returns_request_id(client: AsyncClient):
    request_id = str(uuid.uuid4())
    response = await client.post(
        "/api/v1/analyse",
        headers={"X-Request-ID": request_id},
        json={"text": "A clear and stable deployment survived the outage."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == request_id
    assert response.headers["X-Request-ID"] == request_id
    assert body["backend"] == "deterministic"
    assert body["environment"] == "azure-dev"
    assert body["sentiment"]["label"] == "positive"
    assert "stack" not in response.text.lower()


async def test_validation_error_is_structured(client: AsyncClient):
    response = await client.post("/api/v1/analyse", json={"text": ""})
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert body["request_id"]
    assert body["details"]


async def test_oversized_content_length_is_rejected(client: AsyncClient):
    response = await client.post(
        "/api/v1/analyse",
        headers={"Content-Length": "999999"},
        content=b'{"text":"short"}',
    )
    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"


async def test_health_and_version(client: AsyncClient):
    live = await client.get("/health/live")
    ready = await client.get("/health/ready")
    version = await client.get("/api/v1/version")
    assert live.status_code == 200
    assert ready.json()["status"] == "ready"
    assert version.json()["backend"] == "deterministic"


async def test_fault_requires_token_and_changes_health(client: AsyncClient):
    rejected = await client.post("/internal/faults", json={"mode": "unreadiness", "duration_seconds": 30})
    assert rejected.status_code == 401
    applied = await client.post(
        "/internal/faults",
        headers={"X-Fault-Token": "test-fault-token"},
        json={"mode": "unreadiness", "duration_seconds": 30},
    )
    assert applied.status_code == 200
    ready = await client.get("/health/ready")
    assert ready.status_code == 503
    assert "Traceback" not in ready.text
    live = await client.get("/health/live")
    assert live.status_code == 200


async def test_error_fault_on_analyse(client: AsyncClient):
    await client.post(
        "/internal/faults",
        headers={"X-Fault-Token": "test-fault-token"},
        json={"mode": "errors", "error_status": 500, "duration_seconds": 30},
    )
    response = await client.post("/api/v1/analyse", json={"text": "hello analysis"})
    assert response.status_code == 500
    assert response.json()["error"] == "http_error"
    assert "Traceback" not in response.text


async def test_disabled_fault_endpoint_is_hidden():
    app = create_app(Settings(fault_injection_enabled=False, fault_token="secret"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://analysis") as client:
        response = await client.post(
            "/internal/faults",
            headers={"X-Fault-Token": "secret"},
            json={"mode": "errors"},
        )
    assert response.status_code == 404


async def test_unhandled_error_hides_exception_text(app):
    @app.get("/__boom")
    def boom():
        raise RuntimeError("super-secret-internal-detail")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://analysis") as client:
        response = await client.get("/__boom")
    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert "super-secret-internal-detail" not in response.text
    assert "Traceback" not in response.text


async def test_metrics_endpoint(client: AsyncClient):
    await client.get("/health/live")
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "analysis_http_requests_total" in response.text


async def test_llm_backend_without_key_is_unavailable():
    app = create_app(Settings(analysis_backend="openai", openai_api_key=""))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://analysis") as client:
        response = await client.post("/api/v1/analyse", json={"text": "hello"})
    assert response.status_code == 503
    assert "API key" not in response.text
    assert "sk-" not in response.text
