# ADR 0003: Local processes stand in for AKS and GKE

## Status

Accepted

## Decision

The default environments are two processes of the same analysis image. One is named `azure-dev` and one is named `gcp-dev`. Their `runtime` is `local_container` and their `verification` is `not_cloud_verified`.

Terraform can describe an AKS cluster and a GKE cluster. Those descriptions are not a deployment. The dashboard says so when the runtime is local.

## Why

The failover behaviour has to be reproducible without a cloud bill. Using the same image and the same probes locally means a later cloud deployment changes the network path, not the application contract.

## Consequences

A reviewer must not treat a green local test as evidence that AKS or GKE were used. That evidence would be a Terraform apply output, a `kubectl` context against the real cluster, and a request whose environment field matches that cluster. None of that exists in this repository yet.
