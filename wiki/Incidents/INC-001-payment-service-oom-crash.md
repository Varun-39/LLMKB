---
id: INC-001
title: Payment Service OOM Crash
severity: SEV-1
service: payment-gateway
environment: prod
category: outage
date: 2026-06-02
duration: "47m"
detection_gap: "2m"
tags:
  - incident
  - kubernetes
  - memory
  - oom
  - critical
  - prod
  - payments
error_family: oom
resolution_runbook: RB-001
resolution_outcome: resolved
---

## Summary

All 4 payment-gateway pods were OOMKilled in production between 03:12–03:18 UTC on 2026-06-02. Payment processing was fully down for 47 minutes. ~12,400 transactions failed. Root cause: unbounded idempotency cache introduced in v2.14.0.

## Symptoms

- PagerDuty: `PaymentGateway-PodCrashLooping` at 03:14 UTC
- Memory climbed linearly 78% → 100% over 20 min pre-crash (Grafana)
- HTTP 503 on `/api/v2/payments/process`
- Sentry spike: `java.lang.OutOfMemoryError: Java heap space`
- Downstream timeouts in order-service and notification-service

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~8,200 active transacting users |
| Services degraded | payment-gateway (down), order-service (degraded), notification-service (queuing) |
| Revenue impact | ~$34K failed transactions (majority retried post-recovery) |
| Duration | 03:12 → 03:59 UTC (47 min) |
| Data loss | None — transactions failed cleanly |
| SLA breach | Yes — payments SLA (99.95% uptime) breached |
| Customer comms | Status page updated at 03:20 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 03:12 | First pod OOMKilled (per metrics) |
| 03:14 | Alert fired: `PaymentGateway-PodCrashLooping` |
| 03:15 | On-call acknowledged (Priya Sharma) |
| 03:20 | All 4 pods confirmed OOMKilled, CrashLoopBackOff |
| 03:30 | Root cause identified — unbounded IdempotencyCache |
| 03:35 | Memory limit bumped to 2Gi, rollout restart |
| 03:50 | Hotfix v2.14.1 deployed with cache eviction |
| 03:59 | All pods healthy, service recovered |

## Diagnosis

1. Confirmed OOMKilled state across all replicas
   ```bash
   kubectl get pods -n payments | grep payment-gateway
   # All 4 pods: OOMKilled / CrashLoopBackOff
   ```

2. Verified memory limit was 1Gi (pods hitting ceiling)
   ```bash
   kubectl describe deployment payment-gateway -n payments | grep -A5 "Limits"
   ```

3. Retrieved heap dump (auto-captured via `-XX:+HeapDumpOnOutOfMemoryError`)
   ```bash
   kubectl cp payments/payment-gateway-6d4f8b7c9-abc12:/tmp/heapdump.hprof ./heapdump.hprof
   ```

4. Eclipse MAT analysis: `IdempotencyCache` held 4.2M entries, 780MB

5. Correlated with deployment — v2.14.0 deployed 18:00 UTC previous day
   ```bash
   kubectl rollout history deployment/payment-gateway -n payments
   ```

## Resolution

1. **Mitigate:** Bumped memory limit to 2Gi, restarted deployment
   ```bash
   kubectl set resources deployment/payment-gateway -n payments --limits=memory=2Gi
   kubectl rollout restart deployment/payment-gateway -n payments
   ```

2. **Fix:** Cherry-picked cache eviction patch (max 10K entries, 5-min TTL)
   ```bash
   git cherry-pick b8e2f1a  # PR #1847
   kubectl set image deployment/payment-gateway -n payments \
     payment-gateway=registry.internal/payment-gateway:v2.14.1-hotfix
   ```

3. **Verify:** All pods healthy, endpoint responding
   ```bash
   kubectl get pods -n payments  # 4/4 Running, 0 restarts
   curl -s https://payments.internal/health | jq .status  # "healthy"
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| No progress in 15 min | Page senior on-call | PagerDuty |
| SEV-1 customer impact | Page EM + IC | #incident-response |
| Data integrity risk | Engage DB team | #data-eng |
| Security suspected | Engage SecOps | #security-urgent |

## Post-Incident Review

**What went well:**
- Alert fired within 2 min of first crash
- Runbook was available and followed immediately
- Heap dump auto-captured — no manual intervention needed

**What needs improvement:**
- No pre-crash memory trend alert (only crash alert existed)
- Code review missed unbounded cache in PR #1830
- No canary deployment to catch memory regression

**Contributing factors (beyond root cause):**
- Unbounded `IdempotencyCache` introduced in commit `a3f7c2d` (v2.14.0, deployed 2026-06-01)
- No eviction policy on in-memory caches
- Traffic growth made the cache grow faster than anticipated

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Deploy hotfix v2.14.1 with cache eviction | Priya Sharma | 2026-06-02 | Done |
| Add Grafana alert: memory > 80% sustained 10 min | SRE team | 2026-06-16 | Open |
| Integration test validating cache eviction under load | Priya Sharma | 2026-06-16 | Open |
| Architecture review of all in-memory caches in payment services | Platform team | 2026-06-23 | Open |
| Update RB-001 with heap dump steps | SRE team | 2026-06-16 | Open |

## Links

- Runbooks: [[RB-001-payment-gateway-oom-recovery]]
- Related incidents: [[INC-003-payment-service-memory-leak-recurrence]]
- PR/commit: PR #1847 (cache eviction hotfix)
- Post-mortem doc: N/A
