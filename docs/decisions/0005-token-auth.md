# ADR 0005: Bearer tokens for the MVP

## Status

Accepted

## Decision

The control plane accepts three tokens from the environment: admin, reader, and gateway. Comparison uses `secrets.compare_digest`. Empty tokens never match. The dashboard stores the token in `sessionStorage` and does not contain one.

Mutations (settings, experiments, routing override, immediate probe) require the admin token. Audit events require the admin token. The gateway token can read the current route and write traffic samples. It cannot change settings.

## Why not OIDC yet

There is no identity provider in the local stack. Adding a fake login would look like authorization without being one. Tokens are ugly and appropriate for a single operator. A real deployment should replace them with workload identity for services and a proper user login for the dashboard. The cloud modules already create the workload identities the analysis pod would use; they do not create a user directory.

## Limitations

Anyone who can read the process environment can act as that role. Local compose and the kind overlay use obvious development tokens. Those values are not production secrets, and they must be replaced before any shared deployment.
