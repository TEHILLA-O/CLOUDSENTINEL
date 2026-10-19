# How to test

## Unit and integration

From the repository root, with the virtualenv installed as described in the README:

```powershell
.\.venv\Scripts\python -m pytest -q
```

That run includes:

- analysis API validation, faults, and error redaction
- routing rules: thresholds, cooldown, both environments down, recovery policy
- control-plane authentication and settings validation
- gateway fail-closed behaviour
- a live failover across two analysis processes, the control plane, and the gateway
- Kubernetes manifest checks when `kubectl` is on the PATH

## What the failover test measures

`detection_seconds` is the stored difference between the first failing probe in the window and the routing change. The automated test invokes the monitor immediately, so the number is the cost of three back-to-back probes, not `failure_threshold * health_check_interval`.

On 19 October 2026 that test printed `MEASURED_DETECTION_SECONDS=0.162`. The route moved on the third consecutive application failure, from `azure-dev` to `gcp-dev`, and a request through the gateway was served by `gcp-dev`. After the fault was cleared and recovery was requested, the route returned to `azure-dev` and the incident was resolved.

A separate live run on 19 October 2026 used the default 5 second monitor interval. The dashboard injected `inject_errors` against the Azure stand-in. The stored incident `fde854c4-a6ff-431c-bd5d-a4fa1b58ad2a` recorded `detection_seconds` of 10.165 (failure window started `2026-10-19T11:28:47.892832Z`, routing changed `2026-10-19T11:28:58.058185Z`) and stayed open for 35.391 seconds before automatic recovery returned traffic to `azure-dev`. A gateway request during the failover was served by `gcp-dev`. That 10.165 second figure is a measurement of this interval, not an SLA.

## Kubernetes

```powershell
kubectl kustomize kubernetes/base
kubectl kustomize kubernetes/overlays/local
```

`kubectl kustomize` is covered by `tests/kubernetes`. On 19 October 2026 the Docker engine was not running, so `kind create cluster` and `docker compose up` were not executed. Manifest validation is not a running cluster.

## Terraform

```powershell
terraform fmt -check -recursive infrastructure/terraform
terraform -chdir=infrastructure/terraform/environments/azure-dev init -backend=false
terraform -chdir=infrastructure/terraform/environments/azure-dev validate
terraform -chdir=infrastructure/terraform/environments/gcp-dev init -backend=false
terraform -chdir=infrastructure/terraform/environments/gcp-dev validate
```

`terraform plan` needs cloud credentials and is not run in CI. `terraform apply` is never run by CI.
