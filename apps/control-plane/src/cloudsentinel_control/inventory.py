"""Read nodes and pods from the Kubernetes API.

Inside a cluster the control plane uses its mounted service account. Outside a
cluster it calls kubectl with the configured context. The argument list is
fixed. Request input never becomes a command.
"""

import json
import os
import subprocess
from pathlib import Path

import httpx

from cloudsentinel_control.config import Settings
from cloudsentinel_control.schemas import ClusterInventory, PodInventory

TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
CA_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
NAMESPACE_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")


async def read_cluster(settings: Settings) -> ClusterInventory:
    name = settings.cluster_name or "local"
    if not settings.cluster_inventory_enabled:
        return ClusterInventory(available=False, cluster_name=name, detail="Cluster inventory is turned off.")
    if TOKEN_PATH.is_file() and os.environ.get("KUBERNETES_SERVICE_HOST"):
        try:
            return await _from_api(name)
        except Exception as exc:
            return ClusterInventory(available=False, cluster_name=name, detail=type(exc).__name__)
    if settings.kubectl_context:
        try:
            return _from_kubectl(name, settings.kubectl_context, settings.kubectl_namespace)
        except Exception as exc:
            return ClusterInventory(available=False, cluster_name=name, detail=type(exc).__name__)
    return ClusterInventory(available=False, cluster_name=name, detail="No cluster credentials are mounted.")


async def _from_api(cluster_name: str) -> ClusterInventory:
    host = os.environ["KUBERNETES_SERVICE_HOST"]
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    namespace = NAMESPACE_PATH.read_text(encoding="utf-8").strip() if NAMESPACE_PATH.is_file() else "default"
    headers = {"Authorization": f"Bearer {token}"}
    base = f"https://{host}:{port}"
    async with httpx.AsyncClient(verify=str(CA_PATH), timeout=3.0, headers=headers) as client:
        version = await client.get(f"{base}/version")
        version.raise_for_status()
        nodes = await client.get(f"{base}/api/v1/nodes")
        nodes.raise_for_status()
        pods = await client.get(f"{base}/api/v1/namespaces/{namespace}/pods")
        pods.raise_for_status()
    git_version = version.json().get("gitVersion")
    return _assemble(cluster_name, git_version, nodes.json(), pods.json())


def _from_kubectl(cluster_name: str, context: str, namespace: str) -> ClusterInventory:
    version = _kubectl(context, ["version", "-o", "json"])
    nodes = _kubectl(context, ["get", "nodes", "-o", "json"])
    pods = _kubectl(context, ["get", "pods", "-n", namespace, "-o", "json"])
    server = (version.get("serverVersion") or {}).get("gitVersion")
    return _assemble(cluster_name, server, nodes, pods)


def _kubectl(context: str, args: list[str]) -> dict:
    completed = subprocess.run(
        ["kubectl", "--context", context, *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=8,
        shell=False,
    )
    return json.loads(completed.stdout)


def _assemble(cluster_name: str, version: str | None, nodes: dict, pods: dict) -> ClusterInventory:
    node_items = nodes.get("items") or []
    ready_nodes = sum(1 for node in node_items if _node_ready(node))
    pod_rows = [_pod(item) for item in pods.get("items") or []]
    return ClusterInventory(
        available=True,
        cluster_name=cluster_name,
        kubernetes_version=version,
        node_count=len(node_items),
        ready_node_count=ready_nodes,
        pods=pod_rows,
        detail=None,
    )


def _node_ready(node: dict) -> bool:
    for condition in (node.get("status") or {}).get("conditions") or []:
        if condition.get("type") == "Ready":
            return condition.get("status") == "True"
    return False


def _pod(item: dict) -> PodInventory:
    metadata = item.get("metadata") or {}
    spec = item.get("spec") or {}
    status = item.get("status") or {}
    containers = status.get("containerStatuses") or []
    ready = bool(containers) and all(container.get("ready") for container in containers)
    labels = metadata.get("labels") or {}
    return PodInventory(
        name=metadata.get("name") or "",
        phase=status.get("phase") or "Unknown",
        ready=ready,
        node=spec.get("nodeName"),
        app=labels.get("app.kubernetes.io/name"),
    )
