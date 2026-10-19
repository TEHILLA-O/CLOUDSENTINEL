import json
import re
import subprocess
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cloudsentinel_control.config import Settings
from cloudsentinel_control.models import Environment, ExperimentRecord

# Deployment names are a closed set configured by the operator, then checked
# against this pattern. The request body never reaches the argument list.
DEPLOYMENT_NAME = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")
APPROVED_RUNTIMES = {"local_container", "kind"}

FAULT_BODIES = {
    "inject_latency": lambda body: {
        "mode": "latency",
        "latency_ms": body.latency_ms,
        "error_status": 500,
        "duration_seconds": body.duration_seconds,
    },
    "inject_errors": lambda body: {
        "mode": "errors",
        "latency_ms": 0,
        "error_status": body.error_status,
        "duration_seconds": body.duration_seconds,
    },
    "fail_readiness": lambda body: {
        "mode": "unreadiness",
        "latency_ms": 0,
        "error_status": 503,
        "duration_seconds": body.duration_seconds,
    },
    "fail_liveness": lambda body: {
        "mode": "unliveness",
        "latency_ms": 0,
        "error_status": 503,
        "duration_seconds": body.duration_seconds,
    },
    "clear_faults": lambda body: {
        "mode": "none",
        "latency_ms": 0,
        "error_status": 500,
        "duration_seconds": 0,
    },
}


async def run_experiment(session: AsyncSession, settings: Settings, actor: str, body, client: httpx.AsyncClient) -> ExperimentRecord:
    environment = await session.get(Environment, body.target_environment_id)
    if environment is None:
        raise HTTPException(status_code=404, detail="Environment was not found.")
    # Cloud clusters are out of scope for the dashboard buttons. A flag in the
    # database is not enough on its own; the runtime has to be a local test target.
    if environment.runtime not in APPROVED_RUNTIMES or not environment.experiments_allowed:
        raise HTTPException(
            status_code=403,
            detail="Experiments are restricted to approved local or kind environments.",
        )

    now = datetime.now(timezone.utc)
    record = ExperimentRecord(
        id=str(uuid.uuid4()),
        kind=body.kind,
        target_environment_id=environment.id,
        status="running",
        requested_by=actor,
        parameters={
            "duration_seconds": body.duration_seconds,
            "latency_ms": body.latency_ms,
            "error_status": body.error_status,
        },
        started_at=now,
    )
    session.add(record)
    await session.flush()

    try:
        if body.kind == "restart_local_pods":
            result = _restart_pods(settings, environment.id)
        else:
            result = await _inject(settings, client, environment.base_url, body)
    except HTTPException:
        record.status = "rejected"
        record.finished_at = datetime.now(timezone.utc)
        record.result = {"message": "Experiment was rejected before it ran."}
        raise
    except Exception as exc:
        record.status = "failed"
        record.finished_at = datetime.now(timezone.utc)
        record.result = {"message": "Experiment failed.", "error_type": type(exc).__name__}
        return record

    record.status = "succeeded" if result.get("ok") else "failed"
    record.finished_at = datetime.now(timezone.utc)
    record.result = result
    return record


async def _inject(settings: Settings, client: httpx.AsyncClient, base_url: str, body) -> dict:
    if not settings.fault_token:
        raise HTTPException(status_code=409, detail="FAULT_TOKEN is not configured on the control plane.")
    payload = FAULT_BODIES[body.kind](body)
    response = await client.post(
        f"{base_url.rstrip('/')}/internal/faults",
        headers={"X-Fault-Token": settings.fault_token},
        json=payload,
        timeout=5.0,
    )
    if response.status_code >= 400:
        return {"ok": False, "upstream_status": response.status_code, "message": "The analysis service rejected the fault."}
    applied = response.json()
    return {"ok": True, "upstream_status": response.status_code, "mode": applied.get("mode"), "expires_at": applied.get("expires_at")}


def _restart_pods(settings: Settings, environment_id: str) -> dict:
    if not settings.kubectl_restart_enabled:
        raise HTTPException(
            status_code=409,
            detail="Pod restart is disabled. Enable it only for a named kind context you control.",
        )
    try:
        mapping = json.loads(settings.kubectl_restart_map or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=409, detail="KUBECTL_RESTART_MAP is not valid JSON.") from exc
    deployment = mapping.get(environment_id)
    if not isinstance(deployment, str) or not DEPLOYMENT_NAME.match(deployment):
        raise HTTPException(status_code=409, detail="No approved deployment is configured for this environment.")
    argv = [
        "kubectl",
        "--context",
        settings.kubectl_context,
        "--namespace",
        settings.kubectl_namespace,
        "rollout",
        "restart",
        f"deployment/{deployment}",
    ]
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    output = (completed.stdout or completed.stderr or "").strip()
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "output": output[-400:],
        "argv": argv,
    }
