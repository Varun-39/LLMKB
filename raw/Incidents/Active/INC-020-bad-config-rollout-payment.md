---
id: INC-020
title: Bad Config Rollout — payment-service Rate Limit Set to Zero
severity: SEV-1
service: payment-service
environment: prod
category: deployment-failure
status: resolved
owner: Priya Sharma
assigned-to: Priya Sharma
date: 2026-02-19
duration: 26 minutes
created: 2026-02-19
updated: 2026-02-19
tags:
  - incident
  - deployment
  - config
  - payment-service
  - critical
  - prod
  - payments
related_runbooks:
  - "[[RB-005-failed-deployment]]"
related_incidents:
  - "[[INC-010-release-failed-canary-api]]"
  - "[[INC-011-rollback-failed-frontend]]"
---

# INC-020 — Bad Config Rollout: payment-service Rate Limit Set to Zero

## Summary

At 10:58 UTC on 2026-02-19, a ConfigMap update to payment-service accidentally set `RATE_LIMIT_PER_MIN` to `0` (zero) instead of `600`. The service interpreted `0` as "no limit" and began processing all incoming requests without throttling, including a burst of retry traffic from a downstream client bug. Within 90 seconds the payment-service database connection pool was exhausted by the unthrottled request volume. Payments failed for 26 minutes until the config was corrected and traffic normalized.

## Symptoms

- Grafana: payment-service QPS jumped from 420/min to 4,800/min at 10:58 UTC
- PagerDuty: `PaymentService-ConnectionPoolExhausted` at 11:00 UTC
- payment-service logs: `HikariPool: Connection is not available after 30000ms`
- HTTP 503 rate on `/payments/process`: climbed to 74%
- Postgres `pg_stat_activity`: 200/200 connections held by payment-service
- Client (checkout-service): retry storm — each failed request retried 3× with no backoff

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~5,100 users in active checkout flows |
| Services degraded | payment-service (connection pool exhausted), checkout-service (retry storm) |
| Revenue impact | ~$44K in failed payment attempts |
| Duration | 10:58 → 11:24 UTC (26 min) |
| Data loss | None — all failures were clean rejections |

## Possible Causes

1. **Zero value in ConfigMap** — typo during config update: `RATE_LIMIT_PER_MIN: 0` instead of `600`
2. **Zero interpreted as unlimited** — service treated `0` as "disabled", not as "reject all"
3. **No config validation on apply** — no schema validation step before `kubectl apply` on ConfigMap
4. **Retry storm amplification** — checkout-service retried failed requests 3× without exponential backoff, tripling inbound load

## Troubleshooting Steps

1. Confirmed connection pool exhaustion
   ```bash
   kubectl logs -l app=payment-service -n payments --tail=50 \
     | grep "HikariPool"
   # HikariPool-1 - Connection is not available, request timed out after 30000ms
   ```

2. Identified request rate spike on Grafana — QPS 420 → 4,800/min at 10:58 UTC

3. Reviewed ConfigMap for recent changes
   ```bash
   kubectl get configmap payment-service-config -n payments -o yaml
   # RATE_LIMIT_PER_MIN: "0"
   kubectl describe configmap payment-service-config -n payments | grep "last-applied"
   # kubectl.kubernetes.io/last-applied-configuration: ... updated 10:57 UTC
   ```

4. Confirmed previous value via git history
   ```bash
   git log --oneline -5 -- k8s/prod/payment-service-config.yaml
   git diff HEAD~1 -- k8s/prod/payment-service-config.yaml
   # -RATE_LIMIT_PER_MIN: "600"
   # +RATE_LIMIT_PER_MIN: "0"
   ```

5. Checked checkout-service retry behavior — confirmed 3× immediate retries with no backoff on HTTP 503

## Resolution

1. Corrected ConfigMap and reapplied immediately
   ```bash
   kubectl patch configmap payment-service-config -n payments \
     --type merge -p '{"data":{"RATE_LIMIT_PER_MIN":"600"}}'
   ```

2. Restarted pods to pick up updated config (no live reload for this value)
   ```bash
   kubectl rollout restart deployment/payment-service -n payments
   kubectl rollout status deployment/payment-service -n payments --timeout=120s
   ```

3. Confirmed QPS returned to ~420/min and connection pool released

4. Temporarily reduced checkout-service retry count to 1 while payment-service stabilized

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Payment failure rate >10% for >5 min | Page EM + IC | #incident-response |
| Config change suspected root cause | Revert config immediately, no investigation first | #incident-response |
| DB connections at max | Kill idle payment-service connections on DB if needed | #data-eng |

## Post-Incident Notes

**Went well:**
- Root cause (config typo) identified in 5 minutes via ConfigMap inspection and git diff
- Config patch was applied and effective in under 2 minutes

**Improve:**
- No config validation — zero value should have been rejected as invalid
- Config change applied directly to prod without staging review
- Retry storm made the connection pool impact worse than the config error alone

**Action items:**
- [x] Corrected rate limit config, service recovered
- [ ] Add ConfigMap schema validation (OPA/Kyverno policy: RATE_LIMIT_PER_MIN must be >0)
- [ ] Require config changes to go through staging first (GitOps promotion pipeline)
- [ ] Fix checkout-service retry logic: exponential backoff with jitter, max 3 retries over 30 sec
- [ ] Add alert: payment-service QPS >2× P95 baseline for >1 min

## Related Runbooks

- [[RB-005-failed-deployment]]
