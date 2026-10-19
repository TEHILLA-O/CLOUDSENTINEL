import pytest
from httpx import ASGITransport, AsyncClient

from cloudsentinel_gateway.config import Settings
from cloudsentinel_gateway.main import create_app


@pytest.fixture
async def client():
    app = create_app(Settings(control_plane_url="http://127.0.0.1:9", gateway_token="gateway-token", route_cache_ttl_seconds=0))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway") as http:
            yield http


async def test_gateway_fails_closed_when_the_control_plane_is_down(client: AsyncClient):
    response = await client.post("/api/v1/analyse", json={"text": "hello"})
    assert response.status_code == 503
    assert response.json()["error"] == "no_route"
    assert "Traceback" not in response.text


async def test_gateway_health_does_not_claim_dns_failover(client: AsyncClient):
    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["dns_failover"] is False
