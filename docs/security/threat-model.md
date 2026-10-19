# Threat model

## What we are protecting

The analysis service, the routing decision, and the ability to break a test environment on purpose. The dashboard must not be an unauthenticated remote shell.

## Controls that exist

- Configuration comes from the environment. `.env` is gitignored. `.env.example` holds local placeholders.
- Admin and experiment routes require a bearer token. Tokens are compared in constant time and empty values do not authenticate.
- Experiments are a closed list. They are rejected unless the target runtime is `local_container` or `kind` and `experiments_allowed` is true. AKS and GKE targets are rejected.
- Pod restart is off unless `KUBECTL_RESTART_ENABLED` is set, and the deployment name comes from a server-side map, not from the request body. The process is started with an argument list and `shell=False`.
- Containers in the manifests run as non-root, drop capabilities, and the analysis container uses a read-only root filesystem.
- Service accounts do not mount API tokens unless a later cloud overlay needs workload identity. The cloud Terraform identities for the analysis workload have no extra project roles on GCP, because the service does not call Google APIs. The node service account can write logs, write metrics, and read Artifact Registry.
- Client errors do not include stack traces. The LLM path does not echo the API key.
- Request bodies are size-limited. Inputs are validated with Pydantic.
- Audit rows are written for settings changes, overrides, recovery, experiments, and manual probe ticks.

## Limitations

- Local tokens are shared development values. They are not a production identity system. See ADR 0005.
- The gateway and the control plane are single processes.
- NetworkPolicy resources are present. kind's default CNI does not enforce them. AKS with `network_policy = azure` and GKE with its dataplane would.
- Terraform state for a real AKS cluster contains credential material. It must not be committed. Remote state is documented and not configured.
- API server authorized networks default to empty, which leaves a public Kubernetes API if you apply without editing the example. Do not apply that way.
- Fault injection is enabled on the local stand-ins. Cloud overlays set `FAULT_INJECTION_ENABLED=false`.
- Dependency and image scanning are in CI. They were not all executed on this machine. See the evidence document.
- There is no Web Application Firewall, no mTLS between services, and no customer data isolation story. The analysis text is not stored.
