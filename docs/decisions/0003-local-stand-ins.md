# ADR 0003: Registered services, not labelled stand-ins

## Status

Accepted. Supersedes the earlier decision to present local processes as Azure and GCP.

## Decision

CloudSentinel registers two analysis services, Primary and Secondary. Their ids stay `azure-dev` and `gcp-dev` because routing history already uses those keys. The provider, region, cluster name, and runtime come from the control plane's environment configuration.

`CLUSTER_RUNTIME=kind` means the service is running in the kind cluster. The provider is `kind` until an operator sets it to `azure` or `gcp` for a cluster that is actually in that cloud. The console does not add a disclaimer that the names are fake.

When cluster inventory is enabled, the control plane reads nodes and pods from the Kubernetes API with its own service account. It does not invent node counts.

## Why

Calling a local process "Azure" made the console a demonstration of a deployment that did not exist. The running system is the pair of analysis deployments, the gateway, and the probes. Cloud Terraform remains the way to add a real AKS or GKE environment later, and it is still not applied.

## Consequences

A green local run is evidence about this cluster, not about AKS or GKE. Fault injection stays limited to `local_container` and `kind` runtimes.
