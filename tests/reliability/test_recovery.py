import socket
import threading
import time

import httpx
import pytest
import uvicorn

from analysis_api.config import Settings as AnalysisSettings
from analysis_api.main import create_app as create_analysis
from cloudsentinel_control.config import Settings as ControlSettings
from cloudsentinel_control.main import create_app as create_control
from cloudsentinel_gateway.config import Settings as GatewaySettings
from cloudsentinel_gateway.main import create_app as create_gateway


def _port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class Running:
    def __init__(self, app, port: int):
        self.port = port
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.server.install_signal_handlers = lambda: None
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.server.started:
                return
            time.sleep(0.05)
        raise RuntimeError(f"server on {self.port} did not start")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


@pytest.fixture
def stack(tmp_path):
    azure_port = _port()
    gcp_port = _port()
    control_port = _port()
    gateway_port = _port()
    azure = Running(
        create_analysis(
            AnalysisSettings(
                environment_name="azure-dev",
                environment_provider="azure",
                fault_injection_enabled=True,
                fault_token="fault-token",
            )
        ),
        azure_port,
    )
    gcp = Running(
        create_analysis(
            AnalysisSettings(
                environment_name="gcp-dev",
                environment_provider="gcp",
                fault_injection_enabled=True,
                fault_token="fault-token",
            )
        ),
        gcp_port,
    )
    control = Running(
        create_control(
            ControlSettings(
                database_url=f"sqlite+aiosqlite:///{(tmp_path / 'control.db').as_posix()}",
                monitor_enabled=False,
                admin_token="admin-token",
                reader_token="reader-token",
                gateway_token="gateway-token",
                fault_token="fault-token",
                analysis_azure_url=f"http://127.0.0.1:{azure_port}",
                analysis_gcp_url=f"http://127.0.0.1:{gcp_port}",
                public_gateway_url=f"http://127.0.0.1:{gateway_port}",
                probe_timeout_seconds=2.0,
            )
        ),
        control_port,
    )
    gateway = Running(
        create_gateway(
            GatewaySettings(
                control_plane_url=f"http://127.0.0.1:{control_port}",
                gateway_token="gateway-token",
                route_cache_ttl_seconds=0,
            )
        ),
        gateway_port,
    )
    for server in (azure, gcp, control, gateway):
        server.start()
    try:
        yield {
            "azure": azure_port,
            "gcp": gcp_port,
            "control": control_port,
            "gateway": gateway_port,
            "database": tmp_path / "control.db",
            "control_server": control,
        }
    finally:
        for server in (gateway, control, gcp, azure):
            server.stop()


def _admin() -> dict[str, str]:
    return {"Authorization": "Bearer admin-token"}


async def _tick(client: httpx.AsyncClient, control: int) -> dict:
    response = await client.post(f"http://127.0.0.1:{control}/api/v1/monitor/tick", headers=_admin())
    response.raise_for_status()
    return response.json()


async def _until(client, control, predicate, attempts=8):
    last = None
    for _ in range(attempts):
        last = await _tick(client, control)
        if predicate(last):
            return last
    raise AssertionError(last)


async def test_preferred_failure_moves_traffic_and_records_the_measurement(stack):
    async with httpx.AsyncClient(timeout=10) as client:
        route = await _until(client, stack["control"], lambda item: item["active_environment_id"] == "azure-dev" and item["active_eligible"])
        assert route["active_base_url"].endswith(str(stack["azure"]))

        fault = await client.post(
            f"http://127.0.0.1:{stack['azure']}/internal/faults",
            headers={"X-Fault-Token": "fault-token"},
            json={"mode": "errors", "error_status": 500, "duration_seconds": 120},
        )
        assert fault.status_code == 200
        failed_over = await _until(
            client,
            stack["control"],
            lambda item: item["active_environment_id"] == "gcp-dev" and item["active_eligible"],
        )
        assert failed_over["generation"] >= 2

        # Cache TTL is zero, so this request has to ask the control plane again.
        analysed = await client.post(
            f"http://127.0.0.1:{stack['gateway']}/api/v1/analyse",
            json={"text": "The reliable service recovered after the failure."},
        )
        assert analysed.status_code == 200
        assert analysed.json()["environment"] == "gcp-dev"
        assert analysed.headers["X-CloudSentinel-Environment"] == "gcp-dev"
        assert analysed.headers["X-Request-ID"]

        incidents = await client.get(
            f"http://127.0.0.1:{stack['control']}/api/v1/incidents",
            headers={"Authorization": "Bearer reader-token"},
        )
        assert incidents.status_code == 200
        open_items = [item for item in incidents.json()["items"] if item["status"] == "open"]
        assert open_items
        incident = await client.get(
            f"http://127.0.0.1:{stack['control']}/api/v1/incidents/{open_items[0]['id']}",
            headers={"Authorization": "Bearer reader-token"},
        )
        body = incident.json()
        kinds = {event["kind"] for event in body["events"]}
        assert {"detection", "validation", "routing"} <= kinds
        assert body["to_environment_id"] == "gcp-dev"
        assert body["detection_seconds"] is not None
        assert body["detection_seconds"] >= 0
        # This is the measured value for this run, not a target we invented.
        print(f"MEASURED_DETECTION_SECONDS={body['detection_seconds']}")

        cleared = await client.post(
            f"http://127.0.0.1:{stack['azure']}/internal/faults",
            headers={"X-Fault-Token": "fault-token"},
            json={"mode": "none", "duration_seconds": 0},
        )
        assert cleared.status_code == 200
        await _until(
            client,
            stack["control"],
            lambda item: True,
            attempts=2,
        )
        recover = await client.post(f"http://127.0.0.1:{stack['control']}/api/v1/routing/recover", headers=_admin())
        assert recover.status_code == 200
        restored = await _until(
            client,
            stack["control"],
            lambda item: item["active_environment_id"] == "azure-dev" and item["active_eligible"],
        )
        assert restored["mode"] == "automatic"
        resolved = await client.get(
            f"http://127.0.0.1:{stack['control']}/api/v1/incidents/{open_items[0]['id']}",
            headers={"Authorization": "Bearer reader-token"},
        )
        assert resolved.json()["status"] == "resolved"
        assert any(event["kind"] == "resolution" for event in resolved.json()["events"])

        summary = await client.get(
            f"http://127.0.0.1:{stack['control']}/api/v1/metrics/summary",
            headers={"Authorization": "Bearer reader-token"},
        )
        assert summary.json()["request_count"] >= 1
        assert summary.json()["by_environment"][0]["environment_id"] == "gcp-dev"


async def test_both_environments_down_fails_closed(stack):
    async with httpx.AsyncClient(timeout=10) as client:
        await _until(client, stack["control"], lambda item: item["active_eligible"])
        for port in (stack["azure"], stack["gcp"]):
            response = await client.post(
                f"http://127.0.0.1:{port}/internal/faults",
                headers={"X-Fault-Token": "fault-token"},
                json={"mode": "errors", "error_status": 500, "duration_seconds": 120},
            )
            assert response.status_code == 200
        await _until(client, stack["control"], lambda item: item["active_eligible"] is False, attempts=6)
        analysed = await client.post(
            f"http://127.0.0.1:{stack['gateway']}/api/v1/analyse",
            json={"text": "both environments are down"},
        )
        assert analysed.status_code == 503
        assert analysed.json()["error"] == "no_route"


async def test_slow_responses_fail_over_and_restart_keeps_state(stack):
    async with httpx.AsyncClient(timeout=10) as client:
        await _until(client, stack["control"], lambda item: item["active_environment_id"] == "azure-dev" and item["active_eligible"])
        response = await client.post(
            f"http://127.0.0.1:{stack['azure']}/internal/faults",
            headers={"X-Fault-Token": "fault-token"},
            json={"mode": "latency", "latency_ms": 1200, "duration_seconds": 120},
        )
        assert response.status_code == 200
        moved = await _until(
            client,
            stack["control"],
            lambda item: item["active_environment_id"] == "gcp-dev" and item["active_eligible"],
            attempts=6,
        )
        assert moved["active_environment_id"] == "gcp-dev"

    # The original control-plane process has to release the database before a new one opens it.
    stack["control_server"].stop()
    restarted = Running(
        create_control(
            ControlSettings(
                database_url=f"sqlite+aiosqlite:///{stack['database'].as_posix()}",
                monitor_enabled=False,
                admin_token="admin-token",
                reader_token="reader-token",
                gateway_token="gateway-token",
                fault_token="fault-token",
                analysis_azure_url=f"http://127.0.0.1:{stack['azure']}",
                analysis_gcp_url=f"http://127.0.0.1:{stack['gcp']}",
            )
        ),
        _port(),
    )
    restarted.start()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            current = await client.get(
                f"http://127.0.0.1:{restarted.port}/api/v1/routing/current",
                headers={"Authorization": "Bearer reader-token"},
            )
            assert current.status_code == 200
            assert current.json()["active_environment_id"] == "gcp-dev"
            incidents = await client.get(
                f"http://127.0.0.1:{restarted.port}/api/v1/incidents",
                headers={"Authorization": "Bearer reader-token"},
            )
            assert any(item["status"] == "open" for item in incidents.json()["items"])
    finally:
        restarted.stop()


async def test_readiness_failure_is_classified_separately(stack):
    async with httpx.AsyncClient(timeout=10) as client:
        await _until(client, stack["control"], lambda item: item["active_environment_id"] == "azure-dev")
        response = await client.post(
            f"http://127.0.0.1:{stack['azure']}/internal/faults",
            headers={"X-Fault-Token": "fault-token"},
            json={"mode": "unreadiness", "duration_seconds": 60},
        )
        assert response.status_code == 200
        await _tick(client, stack["control"])
        environments = await client.get(
            f"http://127.0.0.1:{stack['control']}/api/v1/environments/azure-dev",
            headers={"Authorization": "Bearer reader-token"},
        )
        assert environments.json()["last_outcome"] == "readiness_failure"
