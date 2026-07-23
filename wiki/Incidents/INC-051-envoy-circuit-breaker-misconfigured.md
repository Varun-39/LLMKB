---
id: INC-051
title: Envoy Circuit Breaker Tripped Prematurely — Healthy Backend Rejected
severity: SEV-2
service: checkout-service
environment: prod
category: degradation
date: 2026-05-08
duration: "14m"
tags:
  - incident
  - envoy
  - circuit-breaker
  - service-mesh
  - high
  - prod
error_family: unknown
resolution_runbook: RB-017
resolution_outcome: resolved
---

## Summary

At 11:20 UTC on 2026-05-08, Envoy's circuit breaker for the checkout-service upstream tripped due to an overly aggressive `consecutive_5xx` threshold (3 errors). A brief database hiccup caused 3 consecutive 500 responses, tripping the circuit breaker for 60 seconds. During the open state, all requests to checkout-service returned 503 even though the backend had already recovered after 2 seconds.

## Symptoms

- checkout-service: 100% 503 errors for 60-second windows, repeating
- Envoy stats: `upstream_cx_overflow` and `upstream_rq_pending_overflow` incrementing
- Backend pods: healthy, responding normally (verified via direct curl)
- Pattern: 60s outage → 10s recovery → 60s outage (circuit breaker cycling)

## Diagnosis

1. Checked Envoy circuit breaker stats
   ```bash
   kubectl exec checkout-envoy-xyz -n checkout -- curl localhost:15000/stats | grep circuit
   # cluster.checkout-service.circuit_breakers.default.cx_open: 1
   # cluster.checkout-service.upstream_rq_503: 12400
   ```

2. Circuit breaker config: `consecutive_5xx: 3`, `interval: 60s`
   ```bash
   kubectl get destinationrule checkout-service -n checkout -o yaml
   # outlierDetection: consecutive5xxErrors: 3, interval: 60s, baseEjectionTime: 60s
   ```

3. Backend was healthy — issue was the circuit breaker staying open too long

## Resolution

1. **Mitigate:** Disabled outlier detection temporarily
   ```bash
   kubectl patch destinationrule checkout-service -n checkout \
     --type='json' -p='[{"op":"remove","path":"/spec/trafficPolicy/outlierDetection"}]'
   ```

2. **Fix:** Reconfigured with sane values: `consecutive5xxErrors: 10`, `interval: 30s`, `baseEjectionTime: 15s`

3. **Verify:** No more premature circuit breaking during normal error bursts

## Post-Incident Review

- Circuit breaker threshold of 3 errors too aggressive for a service with occasional DB blips
- Standardized circuit breaker settings across all services: 10 consecutive errors, 15s ejection
- Added dashboard showing circuit breaker state per service
- Document: circuit breaker config must account for normal error rate

## Links

- Runbooks: [[RB-017-service-mesh-troubleshooting]]
- Related incidents: [[INC-041-istio-sidecar-injection-failure]]
