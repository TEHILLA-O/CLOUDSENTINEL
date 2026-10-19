import subprocess

import yaml


def _build(path: str) -> list[dict]:
    result = subprocess.run(["kubectl", "kustomize", path], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def test_base_analysis_deployment_is_restricted():
    docs = _build("kubernetes/base")
    deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["resources"]["requests"]["cpu"]
    assert container["resources"]["limits"]["memory"]
    assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert container["startupProbe"]["httpGet"]["path"] == "/health/live"
    assert deployment["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"] == 0
    kinds = {doc["kind"] for doc in docs}
    assert {"HorizontalPodAutoscaler", "PodDisruptionBudget", "NetworkPolicy", "ServiceAccount"} <= kinds


def test_local_overlay_has_two_analysis_services_and_no_shell_escape():
    docs = _build("kubernetes/overlays/local")
    deployments = [doc["metadata"]["name"] for doc in docs if doc["kind"] == "Deployment"]
    assert "analysis-azure" in deployments
    assert "analysis-gcp" in deployments
    assert "control-plane" in deployments
    assert "routing-gateway" in deployments
    rendered = yaml.safe_dump_all(docs)
    assert "kind: Role" not in rendered or "cluster-admin" not in rendered
    assert "cluster-admin" not in rendered


def test_cloud_overlays_disable_fault_injection():
    for path in ("kubernetes/overlays/azure", "kubernetes/overlays/gcp"):
        docs = _build(path)
        deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
        env = {item["name"]: item.get("value") for item in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert env["FAULT_INJECTION_ENABLED"] == "false"
        assert "REPLACE_" in deployment["spec"]["template"]["spec"]["containers"][0]["image"]
