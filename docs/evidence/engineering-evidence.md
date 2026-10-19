# Engineering evidence

Recorded on 19 October 2026 from this machine. Figures below are outputs of commands or of the running processes. They are not targets.

## Status

| Claim | Status |
| --- | --- |
| Analysis API, control plane, routing gateway, dashboard | Implemented and exercised locally |
| Health probes, thresholds, cooldown, incidents, automatic recovery | Implemented and locally tested |
| Gateway as the data plane | Implemented. Not DNS failover |
| Kustomize manifests for local, AKS, and GKE | Implemented. `kubectl kustomize` tested |
| kind cluster and pod restart | Locally tested. Docker Compose was not run |
| Terraform for AKS and GKE | Implemented. `fmt` and `validate` succeeded. `plan` stops without `subscription_id` or `project_id`. Not applied |
| Azure or GCP deployment | Not deployed. Not cloud-verified. No Azure CLI login and no gcloud config on this machine |
| CI on the first push | backend, frontend, kubernetes, and terraform succeeded. images and dependency-scan failed; the causes are fixed in the working tree |
| pip-audit, Trivy, npm audit | Run locally. No known Python vulnerabilities, no unfixed critical image findings, npm audit clean after the dashboard upgrade |

## What was running

Four processes plus the Vite dev server:

- analysis API `azure-dev` on `127.0.0.1:8001`
- analysis API `gcp-dev` on `127.0.0.1:8002`
- control plane on `127.0.0.1:8000`, SQLite `data/control-plane.db`, monitor interval 5 seconds
- routing gateway on `127.0.0.1:8081` (8080 is forbidden on this Windows host)
- dashboard on `http://localhost:5173`

Both environments are local processes. The dashboard banner says so. `verification` on each environment is `not_cloud_verified`.

## Automated tests

```text
.\.venv\Scripts\python -m pytest -q --tb=line
42 passed in 28.53s
```

That includes analysis API tests, the routing engine, control-plane API tests, gateway tests, the scripted failover in `tests/reliability`, and Kubernetes manifest checks.

Dashboard: `npx tsc --noEmit` exited 0. `npm run build` had already succeeded earlier in the same day (Vite reported a large JS bundle warning, not a failed build).

The scripted failover drives the monitor immediately, so it does not wait for the 5 second interval. It printed `MEASURED_DETECTION_SECONDS=0.162`, moved the route from `azure-dev` to `gcp-dev` on the third application error, served a gateway request from `gcp-dev`, then returned to `azure-dev` after recovery. That 0.162 seconds is probe cost, not an operations SLA.

## Live dashboard failover

Signed in at `http://localhost:5173` with `dev-admin-token` (typed into the form; the token is not in the frontend source).

1. Overview listed both stand-ins healthy and the active route `azure-dev`.
2. Analyse from the overview posted to `http://127.0.0.1:8081/api/v1/analyse` and the page showed `azure-dev` in the summary.
3. Reliability page ran `inject_errors` against `azure-dev` for 45 seconds. The experiment record returned `status: succeeded` and the upstream fault API returned mode `errors`.
4. The monitor, on its 5 second loop, opened incident `fde854c4-a6ff-431c-bd5d-a4fa1b58ad2a`.
5. A later gateway request returned `environment=gcp-dev`.
6. After the fault expired, two successful probes, and the cooldown, traffic returned to `azure-dev` and the incident resolved. No manual recover call was made for this run.

Stored timestamps:

| Field | Value |
| --- | --- |
| Failure window started | 2026-10-19T11:28:47.892832Z |
| Routing changed | 2026-10-19T11:28:58.058185Z |
| Resolved | 2026-10-19T11:29:33.449163Z |
| detection_seconds | 10.165 |
| duration_seconds | 35.391 |
| Trigger | application_error |
| From / to | azure-dev / gcp-dev |

Timeline events recorded by the control plane: detection, destination validation, routing change, preferred-environment validation, recovery, resolution.

After recovery the overview showed active route `azure-dev`, both environments healthy, error rate `0.0%` (`0/3` gateway requests), latency p50 `7.459 ms`, p95 `10.928 ms`. The error rate is gateway traffic only. Health-probe failures are not counted as gateway errors, which is why the rate stayed at zero while the incident was an `application_error`.

Screenshots of that session, cropped to the viewport, are in `docs/evidence/screenshots/overview.png` and `docs/evidence/screenshots/incident.png`.

One UI bug showed up and was fixed in the same session: the overview painted "No incidents recorded" while the incidents request was still in flight. It now waits for that request. After the fix, the same page listed the resolved incident.

## Other checks from the same session

- Settings: failure threshold `1` was rejected with `body.failure_threshold: Input should be greater than or equal to 2`. Saving alert latency `900` returned "Saved." It was then set back to `800`. A following `GET /api/v1/settings` showed `alert_latency_ms=800` and `failure_threshold=3`.
- Reader token `dev-reader-token` received HTTP 403 on `POST /api/v1/experiments`.
- Infrastructure page showed both stand-ins, last probe `ok`, and stated that node and pod counts are absent because no Kubernetes API is connected.
- Services page listed both analyse URLs and recent `ok` observations with latencies around 5 ms.

## Example response

`POST http://127.0.0.1:8081/api/v1/analyse` with the text "The reliable cluster recovered after the failure." while `azure-dev` was active:

```json
{
  "environment": "azure-dev",
  "provider": "azure",
  "backend": "deterministic",
  "sentiment": { "label": "neutral", "score": 0.0 },
  "processing_ms": 0.09
}
```

`processing_ms` varies per call. The value above is the one returned in this session, not a benchmark.

## Terraform

`terraform fmt -check -recursive infrastructure/terraform` exited 0.

`terraform validate` in `environments/azure-dev` printed `Success! The configuration is valid.` Provider lock: azurerm 5.10.0. An earlier validate failed because `azurerm_federated_identity_credential` in 5.10 requires `user_assigned_identity_id`. The resource was changed and validate was run again.

`terraform validate` in `environments/gcp-dev` printed the same success line. Provider lock: google 8.7.0.

`terraform plan` and `terraform apply` were not run. No Azure or GCP resources were created.

## Kubernetes

`tests/kubernetes` renders the base and the local, Azure, and GCP overlays with `kubectl kustomize`. Those tests are part of the 42 passes.

After Docker Desktop was started, this machine built `cloudsentinel-analysis:local`, `cloudsentinel-control-plane:local`, and `cloudsentinel-gateway:local`, pulled `postgres:16-alpine`, and created kind cluster `cloudsentinel`. `kind load` and `kubectl apply -k kubernetes/overlays/local` produced five Ready pods. The control-plane log shows HTTP 200 from live, ready, and analyse probes against `http://analysis-azure:8000` and `http://analysis-gcp:8000`.

Pod restart, same Deployment:

| | Name | UID |
| --- | --- | --- |
| Deleted | analysis-azure-667576c665-64l7v | 0f3587f8-d726-4248-9548-0c0d29d2b2af |
| Replacement | analysis-azure-667576c665-rsf8v | dad5f80c-c11f-4d61-a186-ee6b54746f15 |

`kubectl rollout status` reported success. `kubectl exec` against the new pod received HTTP 200 from `/health/live`. This is a local kind cluster, not AKS or GKE. kind does not enforce the NetworkPolicies.

## Scans

`pip-audit` (19 October 2026): `No known vulnerabilities found`. The three local packages are skipped because they are not published on PyPI.

`npm audit --audit-level=high` initially failed. `braces` `<=3.0.3` has no patched release and was pulled in by Tailwind 3. The dashboard now uses Tailwind 4 and React Router 7.18.4. A following `npm audit` reported `found 0 vulnerabilities`, and `npm run build` succeeded.

Trivy 0.76.0, `--severity CRITICAL --ignore-unfixed --pkg-types os,library`, exit code 0 for all three application images. The GitHub `images` workflow had pinned `aquasecurity/trivy-action@0.28.0`, which is not a published tag. It is now `v0.36.0`.

## Terraform plan

`terraform plan -input=false` in `azure-dev` stopped with: required variable `subscription_id` is not set. `gcp-dev` stopped the same way on `project_id`. There is no `terraform.tfvars`, no Azure CLI, and no gcloud config on this machine. No plan was produced and nothing was applied.

## Why the pieces are shaped this way

- Kustomize rather than Helm: one deployment shape, three overlays, no chart runtime. See `docs/decisions/0001-kustomize.md`.
- The gateway is the data plane because DNS failover is not implemented. The gateway is a single process and can fail on its own. See `docs/decisions/0002-gateway-data-plane.md`.
- Three consecutive failures, two successes, and a cooldown exist so one slow probe does not move traffic. The first route selection does not start the cooldown, or the system could not fail over immediately after startup. See `docs/decisions/0004-failure-thresholds.md`.
- Tokens rather than an identity provider: the mutations need an authorization boundary, and standing up OIDC was more moving parts than this MVP needs. See `docs/decisions/0005-token-auth.md`.
- If both environments are ineligible, the last environment id can remain stored but `active_eligible` is false and the gateway returns 503.
- Experiments accept a closed set of kinds and only `local_container` or `kind` runtimes. There is no shell field.

## What a reviewer should not infer

A Terraform validate, a local process named `azure-dev`, or a Kustomize overlay is not an AKS or GKE deployment. Cloud verification starts only after an explicit apply, a workload on that cluster, and a test against it.
