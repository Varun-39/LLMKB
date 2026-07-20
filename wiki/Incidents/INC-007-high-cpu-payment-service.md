---
id: INC-007
title: High CPU on payment-service — Regex Backtracking
severity: SEV-2
service: payment-service
environment: prod
category: degradation
date: 2026-05-06
duration: "38m"
detection_gap: "2m"
tags:
  - incident
  - cpu
  - performance
  - payment-service
  - high
  - prod
  - payments
---

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
| SLA breach | No — degradation, not full outage |
| Customer comms | N/A — no status page update |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 16:05 | CPU saturation began across all payment-service pods |
| 16:07 | Alert fired: `PaymentService-CPUThrottled` |
| 16:08 | On-call acknowledged (Priya Sharma) |
| 16:12 | Thread dump captured — regex backtracking identified |
| 16:18 | Root cause confirmed — catastrophic regex in CardValidator |
| 16:25 | Immediate mitigation: 200ms request timeout applied |
| 16:38 | Hotfix v5.1.1 deployed with safe validation logic |
| 16:43 | CPU baseline restored, latency normalized |

## Diagnosis

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

3. Identified hot code path via async-profiler output
   - `CardValidator.validateNumber()` consuming 94% of CPU cycles
   - Regex: `^([0-9]{4}[\s-]?){3}[0-9]{4}$`

4. Reproduced locally — input `"1234 1234 1234 123"` (15 digits, missing last) caused ~8s match attempt

5. Correlated with v5.1.0 release — CardValidator regex changed from simple digit check to grouped format check

## Resolution

1. **Mitigate:** Added request timeout of 200ms on validation endpoint to prevent thread starvation
   ```bash
   kubectl set env deployment/payment-service -n payments VALIDATE_TIMEOUT_MS=200
   kubectl rollout restart deployment/payment-service -n payments
   ```

2. **Fix:** Replaced catastrophic regex with linear-time validation logic (PR #2388, v5.1.1)
   ```bash
   kubectl set image deployment/payment-service -n payments \
     payment-service=registry.internal/payment-service:v5.1.1
   ```

3. **Verify:** Confirmed CPU returned to baseline (~15%) and latency normalized
   ```bash
   kubectl top pods -n payments -l app=payment-service
   # payment-service pods: ~300m CPU
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| CPU >90% for >10 min with no fix | Escalate to senior on-call | PagerDuty |
| Payment failure rate >10% | Page EM + IC | #incident-response |
| Cannot deploy fix within 30 min | Consider rolling back to v5.0.x | #incident-response |

## Post-Incident Review

**What went well:**
- CPU alert fired quickly
- Thread dump immediately identified hot code path
- async-profiler output made root cause unambiguous

**What needs improvement:**
- No regex complexity review in code review process
- PR adding new regex had no performance test
- Canary deployment would have caught this pre-rollout

**Contributing factors (beyond root cause):**
- Catastrophic regex susceptible to exponential backtracking on partial input
- No static analysis for regex complexity in CI pipeline
- No load testing of validation endpoint with edge-case inputs

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Deploy v5.1.1 with safe validation logic | Priya Sharma | 2026-05-06 | Done |
| Add static analysis rule flagging potentially catastrophic regexes | Platform team | 2026-05-20 | Open |
| Add performance benchmark to payment validation unit tests | Priya Sharma | 2026-05-20 | Open |
| Enable canary deployments for payment-service changes | SRE team | 2026-05-27 | Open |

## Links

- Runbooks: [[RB-004-high-cpu-usage]]
- Related incidents: [[INC-013-k8s-pending-pods-resource-pressure]]
- PR/commit: PR #2388 (regex fix)
- Post-mortem doc: N/A
