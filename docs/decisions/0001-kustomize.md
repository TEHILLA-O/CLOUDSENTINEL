# ADR 0001: Kustomize for Kubernetes configuration

## Status

Accepted

## Decision

Kubernetes configuration uses Kustomize. The base describes one analysis deployment. Azure and GCP overlays change the image, the environment name, and the workload-identity annotation. The local overlay is a different topology: two analysis deployments plus Postgres, the control plane, and the gateway.

## Why not Helm

The differences between environments are image names, a handful of environment variables, and identity annotations. Kustomize patches express that without a chart release process or templating language. Helm would be justified if we were packaging this for other teams to install with many parameters. We are not.

## Consequences

Cloud overlays contain `REPLACE_` placeholders. They are not applied as-is. The local overlay duplicates the analysis pod spec instead of rendering the base twice under two names, because one Kustomize base cannot emit two differently named copies of the same deployment without a second overlay.
