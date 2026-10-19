# ADR 0002: A reverse proxy is the data plane

## Status

Accepted

## Decision

The routing gateway is a single FastAPI process. It asks the control plane which environment is eligible and proxies `/api/v1/analyse` and `/api/v1/version` there. It records the result back to the control plane.

## What this is not

This is not global DNS failover, not a multi-region load balancer, and not Traffic Manager or Cloud DNS. The gateway is a single point of failure. If it stops, new requests stop even when both analysis services are healthy.

If the control plane cannot be reached, the gateway keeps the last decision for 30 seconds and then fails closed. A decision that says the active environment is not eligible is never cached as a healthy route.

## Why this shape

The behaviour we need to demonstrate is: detect sustained failure, check the other environment, and send the next request there. A proxy makes that observable on one machine. DNS failover would hide the decision in a resolver cache and would require cloud resources we have not been approved to create.
