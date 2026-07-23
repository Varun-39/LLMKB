---
id: INC-085
title: gRPC Max Message Size Exceeded Causing Silent Request Drops
severity: SEV-2
service: reporting-service
environment: prod
category: degradation
date: 2026-04-11
duration: "2h 10m"
tags:
  - incident
  - grpc
  - message-size
  - silent-failure
  - reporting-service
  - prod
error_family: unknown
resolution_runbook: RB-017
resolution_outcome: resolved
---

## Summary

The reporting-service gRPC server had a default `MaxRecvMsgSize` of 4 MB. A new report type introduced large payloads (up to 11 MB) that silently exceeded this limit. gRPC returned `RESOURCE_EXHAUSTED` to the client but the calling service treated it as a transient error and retried indefinitely, generating a silent retry storm that delayed report delivery for 2+ hours without any alert firing.

## Symptoms

- Users: "Report generation is stuck / never completes"
- reporting-service logs: `rpc error: code = ResourceExhausted desc = grpc: received message larger than max`
- Calling service (api-gateway) retry loop: no circuit breaker, retrying every 2 seconds
- No alert fired — error was classified as `transient` in retry logic

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~340 users waiting on large reports |
| Services degraded | reporting-service (large reports), api-gateway (retry overhead) |
| Revenue impact | N/A |
| Duration | 10:00 → 12:10 UTC (2h 10m) |
| Data loss | None |
| SLA breach | Yes — report SLA (4h) not breached but internal 30-min target missed |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 10:00 | New report type deployed with large payload |
| 10:02 | First RESOURCE_EXHAUSTED errors begin |
| 10:05 | api-gateway begins silent retry loop |
| 11:50 | User complaint ticket raised |
| 12:00 | On-call began investigation |
| 12:10 | MaxRecvMsgSize increased, reports processed |

## Diagnosis

1. Found RESOURCE_EXHAUSTED errors in reporting-service logs:
   ```bash
   kubectl logs -n reporting deploy/reporting-service | grep RESOURCE_EXHAUSTED
   # rpc error: code = ResourceExhausted desc = grpc: received message larger than max (11534336 vs 4194304)
   ```
2. Confirmed client retry loop without backoff or dead-letter:
   ```bash
   grep -r "ResourceExhausted" src/gateway/grpc_client.go
   # case codes.ResourceExhausted: return retry(req)  // BUG: should not retry on size error
   ```
3. Identified new report type as source (payload size 11 MB):
   ```bash
   kubectl logs -n reporting deploy/reporting-service | grep "report_type=quarterly_summary" | wc -l
   # 8441  — all failed attempts
   ```

## Resolution

1. **Mitigate:** Increased `MaxRecvMsgSize` to 64 MB on gRPC server
   ```bash
   kubectl set env deployment/reporting-service -n reporting GRPC_MAX_RECV_MSG_SIZE=67108864
   kubectl rollout restart deployment/reporting-service -n reporting
   ```
2. **Fix in api-gateway:** `ResourceExhausted` treated as permanent failure, not transient
3. **Verify:** Queued reports drained within 15 minutes
   ```bash
   kubectl logs -n reporting deploy/reporting-service | grep "report_type=quarterly_summary" | grep -c "success"
   # 340
   ```

## Post-Incident Review

**What went well:**
- Root cause was clear once logs were examined

**What needs improvement:**
- `RESOURCE_EXHAUSTED` should never be retried without size change — classic non-retryable error
- No alert on sustained gRPC error codes
- Large payloads shipped without gRPC size validation in CI

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Fix retry classification: RESOURCE_EXHAUSTED is non-retryable | Backend | 2026-04-18 | Open |
| Add gRPC error rate alert by code (RESOURCE_EXHAUSTED, UNIMPLEMENTED) | Observability | 2026-04-18 | Open |
| Add payload size assertion in report generation unit tests | Backend | 2026-04-25 | Open |

## Links

- Runbooks: [[RB-017-service-mesh-troubleshooting]]
- Related incidents: [[INC-043-grpc-deadline-exceeded-cascade]]
