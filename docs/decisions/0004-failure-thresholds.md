# ADR 0004: Thresholds, hysteresis, and cooldown

## Status

Accepted

## Decision

An environment is not eligible until `success_threshold` consecutive successful probes (default 2). It stays eligible through fewer than `failure_threshold` hard failures (default 3) and fewer than `latency_breach_threshold` slow probes (default 3). Crossing either threshold opens a circuit and removes eligibility.

Hard failures and latency do not share a counter. A timeout is not the same event as a slow 200.

The cooldown starts when traffic moves from one active environment to another. It does not start on the first selection, because that would block a genuine failover during the first half minute. Recovery to the preferred environment waits for the cooldown unless an admin calls `POST /api/v1/routing/recover`.

Traffic is not moved until the destination is eligible. If none is, the gateway returns 503.

## Measurement

`detection_seconds` on an incident is `routing_changed_at - failure_window_started_at`. It is computed from stored timestamps. A test that ticks the monitor immediately measures the probe loop, not the configured interval. With the default 5 second interval, three consecutive failures are about two intervals of wall clock plus probe time.
