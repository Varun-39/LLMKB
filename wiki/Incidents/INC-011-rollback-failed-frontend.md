---
id: INC-011
title: Rollback Failed — payment-service DB Migration Not Reverted
severity: SEV-1
service: payment-service
environment: prod
category: deployment-failure
date: 2026-04-12
duration: "1h 13m"
detection_gap: "1m"
tags:
  - incident
  - deployment
  - rollback
  - database
  - critical
  - prod
  - payments
error_family: unknown
resolution_runbook: RB-006
resolution_outcome: partial
---

## Summary

On 2026-04-12, a failed payment-service v6.0.0 deployment was rolled back at the application layer but the associated Postgres migration (adding a non-nullable `payment_method_type` column) was not reverted. The rolled-back v5.9.3 code did not populate this column, causing 100% of payment writes to fail for 73 minutes until a compatibility shim migration was applied.

## Symptoms

- PagerDuty: `PaymentService-HighErrorRate` fired at 18:44 UTC
- payment-service logs: `ERROR: null value in column "payment_method_type" violates not-null constraint`
- HTTP 500 on all `POST /payments/initiate` requests (100% failure rate)
- Grafana: payment success rate dropped to 0% immediately after rollback at 18:43 UTC
- No pod crashes — service running, all errors at DB write layer

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All users initiating payments (~3,800 attempts in 73-min window) |
| Services degraded | payment-service (writes down), checkout-service (fully blocked) |
| Revenue impact | ~$67K in failed payment attempts (majority retried post-recovery) |
| Duration | 18:43 → 19:56 UTC (73 min) |
| Data loss | None — all failures rejected at constraint level, no partial writes |
| SLA breach | Yes — payments SLA (99.95% uptime) breached |
| Customer comms | Status page updated at 18:52 UTC; customer success notified enterprise accounts |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 18:30 | payment-service v6.0.0 deployed (included DB migration) |
| 18:38 | Critical bug discovered in v6.0.0 reporting path |
| 18:43 | Rollback to v5.9.3 executed (application only, not DB) |
| 18:44 | Alert fired — 100% payment write failures |
| 18:45 | On-call acknowledged (Priya Sharma) |
| 18:53 | Root cause identified — non-nullable column incompatible with v5.9.3 |
| 19:10 | Decision made: apply compatibility migration (make column nullable) |
| 19:52 | ALTER TABLE applied, writes resumed immediately |
| 19:56 | Error rate 0%, incident closed |

## Diagnosis

1. Confirmed 100% error rate on payment writes
   ```bash
   kubectl logs -l app=payment-service -n payments --tail=50
   # ERROR: null value in column "payment_method_type" violates not-null constraint
   # Detail: Failing row contains (uuid, user_id, amount, NULL, ...)
   ```

2. Verified application was running rolled-back version
   ```bash
   kubectl get deploy payment-service -n payments -o jsonpath='{.spec.template.spec.containers[0].image}'
   # registry.internal/payment-service:v5.9.3
   ```

3. Checked current schema — confirmed migration column still present
   ```bash
   psql -U postgres -d payments_db -c "\d payment_transactions"
   # payment_method_type | character varying(50) | not null  ← added by v6.0.0 migration
   ```

4. Verified no down migration existed
   ```bash
   ls db/migrations/ | grep rollback
   # No results — no down migration provided
   ```

## Resolution

1. **Mitigate:** Applied emergency compatibility migration — made column nullable with default
   ```bash
   psql -U postgres -d payments_db -c "
     ALTER TABLE payment_transactions
       ALTER COLUMN payment_method_type DROP NOT NULL,
       ALTER COLUMN payment_method_type SET DEFAULT 'unknown';"
   ```

2. **Fix:** Scheduled proper down migration + v6.1.0 plan for next deploy window to address root schema issue

3. **Verify:** Confirmed payment writes succeeding
   ```bash
   psql -U postgres -d payments_db -c "
     INSERT INTO payment_transactions (id, user_id, amount) VALUES (gen_random_uuid(), 1, 100.00);"
   # INSERT 0 1 — success
   kubectl logs -l app=payment-service -n payments --tail=20
   # No errors — error rate 0%
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Rollback causes new failure within 5 min | Page EM + IC immediately | #incident-response |
| DB schema conflict suspected | Engage DBA team | #data-eng |
| Revenue services down >15 min | Executive escalation | PagerDuty P1 policy |

## Post-Incident Review

**What went well:**
- Root cause identified within 8 min (clear error message, fast DB inspection)
- ALTER TABLE fix applied with zero additional downtime

**What needs improvement:**
- No down migration existed — migration strategy policy not enforced
- Rollback checklist did not mention DB migration state
- v6.0.0 deploy was not backward compatible by design

**Contributing factors (beyond root cause):**
- Team assumed application-only rollback was sufficient
- No automated post-rollback smoke test that validates DB writes
- Deployment pipeline lacked migration/rollback coupling checks

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Mandate backward-compatible migrations (expand-then-contract pattern) | Priya Sharma | 2026-04-26 | Open |
| Add DB migration state check to rollback runbook | SRE team | 2026-04-19 | Open |
| Require down migration for every up migration in PR checklist | Platform team | 2026-04-26 | Open |
| Add post-rollback smoke test to deployment pipeline | CI/CD team | 2026-05-03 | Open |

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]], [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-018-db-lock-contention-payments]]
- PR/commit: N/A
- Post-mortem doc: N/A
