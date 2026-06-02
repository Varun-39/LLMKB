---
id: INC-007
title: High CPU on payment-service — Regex Backtracking
severity: SEV-2
service: payment-service
environment: prod
category: degradation
status: resolved
owner: Priya Sharma
assigned-to: Priya Sharma
date: 2026-05-06
duration: 38 minutes
created: 2026-05-06
updated: 2026-05-06
tags:
  - incident
  - cpu
  - performance
  - payment-service
  - high
  - prod
  - payments
related_runbooks:
  - "[[RB-003-high-cpu]]"
related_incidents: []
---

# INC-007 — High CPU on payment-service: Regex Backtracking

## Summary

All payment-service pods experienced CPU saturation at 16:05 UTC on 2026-05-06, with all 8 vCPUs pegged at 98–100% per pod. P99 latency on `/payments/validate` climbed from 90 ms to 11 s. Root cause was a catastrophic regex backtracking bug introduced in v5.1.0 when validating card number input — a crafted or malformed input string could cause exponential regex evaluation time. Deployed fix in 38 minutes.

## Symptoms

- PagerDuty: `PaymentService-CPUThrottled` at 16:07 UTC
- Grafana: CPU usage across all payment-service pods at 98–100%
- P99 latency on `/payments/validate`: 90 ms → 11 s
- HTTP 504 timeout errors: ~23% of requests
- Thread dump: hundreds of threads stuck in `java.util.regex.Pattern.match()`
- No memory pressure — purely CPU-bound

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~5,400 users mid-checkout |
| Services degraded | payment-service (severely degraded), checkout-service (timeouts) |
| Revenue impact | ~$28K in failed or timed-out payment attempts |
| Duration | 16:05 → 16:43 UTC (38 min) |
| Data loss | None — validation failures rejected cleanly |

## Possible Causes

1. **Catastrophic regex backtracking** — new card validation regex `^([0-9]{4}[\s-]?){3}[0-9]{4}$` susceptible to exponential backtracking on partial input
2. **Sudden traffic spike** — flash sale event increasing concurrent validation requests
3. **Underlying JVM thread pool exhaustion** — CPU pressure from GC combined with high thread count
4. **Third-party fraud-check library** — updated in v5.1.0, CPU-intensive fingerprinting

## Troubleshooting Steps

1. Confirmed CPU saturation
   ```bash
   kubectl top pods -n payments -l app=payment-service
   # payment-service-xxx  2000m/2000m CPU (100%)
   ```

2. Captured thread dump
   ```bash
   kubectl exec payment-service-6f7d-rp21 -n payments -- kill -3 1
   kubectl logs payment-service-6f7d-rp21 -n payments | grep -A5 "regex"
   # Hundreds of threads in java.util.regex.Pattern.match()
   ```

3. Identified hot code path via async-profiler output (attached in Assets/)
   - `CardValidator.validateNumber()` consuming 94% of CPU cycles
   - Regex: `^([0-9]{4}[\s-]?){3}[0-9]{4}$`

4. Reproduced locally — input `"1234 1234 1234 123"` (15 digits, missing last) caused ~8s match attempt

5. Correlated with v5.1.0 release — CardValidator regex changed from simple digit check to grouped format check

## Resolution

1. **Immediate mitigation:** Added request timeout of 200ms on validation endpoint to prevent thread starvation
   ```bash
   kubectl set env deployment/payment-service -n payments VALIDATE_TIMEOUT_MS=200
   kubectl rollout restart deployment/payment-service -n payments
   ```

2. **Fix:** Replaced catastrophic regex with linear-time validation logic (PR #2388, v5.1.1)
   ```bash
   kubectl set image deployment/payment-service -n payments \
     payment-service=registry.internal/payment-service:v5.1.1
   ```

3. Confirmed CPU returned to baseline (~15%) and latency normalized
   ```bash
   kubectl top pods -n payments -l app=payment-service
   # payment-service pods: ~300m CPU
   ```

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| CPU >90% for >10 min with no fix | Escalate to senior on-call | PagerDuty |
| Payment failure rate >10% | Page EM + IC | #incident-response |
| Cannot deploy fix within 30 min | Consider rolling back to v5.0.x | #incident-response |

## Post-Incident Notes

**Went well:**
- CPU alert fired quickly
- Thread dump immediately identified hot code path
- async-profiler output made root cause unambiguous

**Improve:**
- No regex complexity review in code review process
- PR adding new regex had no performance test
- Canary deployment would have caught this pre-rollout

**Action items:**
- [x] Deployed v5.1.1 with safe validation logic
- [ ] Add static analysis rule flagging potentially catastrophic regexes
- [ ] Add performance benchmark to payment validation unit tests
- [ ] Enable canary deployments for payment-service changes

## Related Runbooks

- [[RB-003-high-cpu]]
