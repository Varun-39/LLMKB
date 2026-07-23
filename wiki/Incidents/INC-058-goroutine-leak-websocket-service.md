---
id: INC-058
title: Goroutine Leak in WebSocket Service — 2M Goroutines Before OOM
severity: SEV-2
service: realtime-service
environment: prod
category: degradation
date: 2026-05-22
duration: "35m"
tags:
  - incident
  - golang
  - goroutine
  - leak
  - websocket
  - memory
  - high
  - prod
error_family: oom
resolution_runbook: RB-002
resolution_outcome: resolved
---

## Summary

The realtime-service (Go) accumulated 2 million goroutines over 3 days due to a leaked goroutine in the WebSocket disconnect handler. Each client disconnect spawned a goroutine to flush buffered messages, but the goroutine blocked indefinitely on a closed channel. Memory grew linearly from 200MB to 6GB until the pod was OOMKilled.

## Symptoms

- PagerDuty: `RealtimeService-MemoryHigh` at 11:00 UTC
- pprof: 2,040,000 active goroutines (normal: ~5,000)
- Memory: 6GB (limit: 8GB, growing)
- WebSocket connections: functioning normally (leak was background goroutines)

## Diagnosis

1. Captured goroutine profile
   ```bash
   kubectl port-forward realtime-service-xyz -n realtime 6060:6060
   curl http://localhost:6060/debug/pprof/goroutine?debug=1 | head -50
   # 2,040,000 goroutines blocked at flushBuffer:87 — chan receive on closed channel
   ```

2. Code review: `flushBuffer` goroutine reads from `client.outbound` channel which is closed on disconnect but never checked

3. Leak rate: ~450 goroutines/minute (one per client disconnect)

## Resolution

1. **Mitigate:** Restart pods (clears leaked goroutines)
   ```bash
   kubectl rollout restart deployment/realtime-service -n realtime
   ```

2. **Fix:** Added context cancellation to flush goroutine — exits when client disconnects

3. **Verify:** Goroutine count stable at ~5,000 after fix deployed

## Post-Incident Review

- Go's goroutine model makes leaks silent until OOM
- Added `/debug/pprof` endpoint monitoring: alert if goroutine count >20,000
- Added `goleak` test in CI to catch goroutine leaks in unit tests
- Code review checklist now includes: "Does every goroutine have a termination condition?"

## Links

- Runbooks: [[RB-002-kubernetes-oom-remediation]]
- Related incidents: [[INC-001-payment-service-oom-crash]]
