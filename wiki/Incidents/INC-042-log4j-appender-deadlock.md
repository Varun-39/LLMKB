---
id: INC-042
title: Log4j Async Appender Deadlock — Payment Service Hung Threads
severity: SEV-1
service: payment-service
environment: prod
category: outage
date: 2026-04-02
duration: "28m"
detection_gap: "4m"
tags:
  - incident
  - java
  - logging
  - deadlock
  - payment
  - critical
  - prod
error_family: unknown
resolution_runbook: RB-007
resolution_outcome: resolved
---

## Summary

At 11:42 UTC on 2026-04-02, the payment-service became unresponsive due to a deadlock in the Log4j2 async appender. The ring buffer filled when the Fluentd sidecar became temporarily unreachable (network blip), and all application threads blocked waiting to write log entries. The service appeared healthy (pod running, liveness probe passing via TCP) but could not process any requests for 28 minutes.

## Symptoms

- PagerDuty: `PaymentService-HighLatency` at 11:46 UTC
- payment-service: 100% request timeout (no 500s, just timeouts)
- Pod status: Running (liveness TCP probe passing)
- Thread dump: all request threads BLOCKED on `org.apache.logging.log4j.core.async.AsyncLoggerDisruptor`
- Fluentd sidecar: `connection refused` errors at 11:41 (resolved by 11:43)

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~5,500 users attempting payments |
| Services degraded | payment-service (fully unresponsive) |
| Revenue impact | ~$22K in failed transactions |
| Duration | 11:42 → 12:10 UTC (28 min) |
| Data loss | None — transactions timed out cleanly |
| SLA breach | Yes — payments SLA breached |
| Customer comms | Status page updated at 11:50 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 11:41 | Fluentd sidecar lost connection to log aggregator (2-min blip) |
| 11:42 | Log4j ring buffer full, application threads begin blocking |
| 11:43 | Fluentd connection restored, but ring buffer already full |
| 11:46 | Alert fired: `PaymentService-HighLatency` |
| 11:48 | On-call acknowledged (Alex Kim) |
| 11:55 | Thread dump captured, deadlock identified |
| 12:00 | Pods restarted with `FORCE_SYNC_LOGGING=false` |
| 12:05 | Payment processing resumed |
| 12:10 | Error rate at baseline, incident closed |

## Diagnosis

1. Confirmed service unresponsive
   ```bash
   curl -w "%{http_code}" --max-time 5 http://payment-service.payments:8080/health
   # Timed out (TCP connect works, HTTP hangs)
   ```

2. Captured thread dump
   ```bash
   kubectl exec payment-service-abc -n payments -- kill -3 1
   kubectl logs payment-service-abc -n payments | grep -A5 "BLOCKED"
   # 48/48 request threads BLOCKED at AsyncLoggerDisruptor.publish
   ```

3. Ring buffer diagnostics
   ```bash
   kubectl exec payment-service-abc -n payments -- \
     jcmd 1 VM.flags | grep RingBuffer
   # RingBufferSize=4096 (too small for burst)
   ```

## Resolution

1. **Mitigate:** Restart pods (clears the deadlock)
   ```bash
   kubectl rollout restart deployment/payment-service -n payments
   ```

2. **Fix:** Changed Log4j config to use `DISCARD` policy when ring buffer full (drop logs instead of blocking threads)

3. **Verify:** Confirmed processing resumed
   ```bash
   curl -s http://payment-service.payments:8080/health | jq .status
   # "healthy"
   ```

## Post-Incident Review

- Log4j async appender default behavior blocks threads when buffer full
- Changed to `DISCARD` overflow policy: lose logs, not transactions
- Increased ring buffer from 4096 to 65536
- Added HTTP-based liveness probe (not TCP) to detect hung threads
- Added alert: if all request threads are BLOCKED for >30s

## Links

- Runbooks: [[RB-007-pod-crash-investigation]]
- Related incidents: [[INC-001-payment-service-oom-crash]]
