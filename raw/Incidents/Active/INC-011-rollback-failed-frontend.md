---
id: INC-011
title: Rollback Failed — frontend-service DB Migration Not Reverted
severity: SEV-1
service: payment-service
environment: prod
category: deployment-failure
status: resolved
owner: Priya Sharma
assigned-to: Priya Sharma
date: 2026-04-12
duration: 73 minutes
created: 2026-04-12
updated: 2026-04-12
tags:
  - incident
  - deployment
  - rollback
  - database
  - critical
  - prod
  - payments
related_runbooks:
  - "[[RB-005-failed-deployment]]"
  - "[[RB-004-db-timeouts]]"
related_incidents:
  - "[[INC-010-release-failed-canary-api]]"
---

# INC-011 — Rollback Failed: frontend-service DB Migration Not Reverted

## Summary

On 2026-04-12, a failed payment-service v6.0.0 deployment was rolled back at the application layer but the associated Postgres migration (adding a non-nullable `payment_method_type` column) was not reverted. The rolled-back v5.9.3 application did not know about this column and began failing on all INSERT statements with a `not-null constraint violation`. The service was down for 73 minutes until a compatibility shim migration was applied to make the column nullable.

## Symptoms

- PagerDuty: `PaymentService-HighErrorRate` at 18:44 UTC
- payment-service logs: `ERROR: null value in column "payment_method_type" violates not-null constraint`
- HTTP 500 on all `POST /payments/initiate` requests (100% failure rate)
- Grafana: payment success rate dropped to 0% immediately after rollback at 18:43 UTC
- No pod crashes — service running, all errors at DB write layer

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All users initiating payments (~3,800 attempts in 73-min window) |
| Services degraded | payment-service (writes down), checkout-service (fully blocked) |
| Revenue impact | ~$67K in failed payment attempts (majority retried successfully post-recovery) |
| Duration | 18:43 → 19:56 UTC (73 min) |
| Data loss | None — all failures were rejected at constraint level, no partial writes |

## Possible Causes

1. **Forward-only migration** — migration added non-nullable column without a compensating down migration
2. **Deployment checklist gap** — rollback procedure did not include a step to revert DB migrations
3. **No migration compatibility layer** — v6.0.0 migration not written to be backward compatible with v5.9.3
4. **Insufficient staging validation** — rollback scenario not tested in staging prior to prod deploy

## Troubleshooting Steps

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

3. Checked current schema state
   ```bash
   psql -U postgres -d payments_db -c "\d payment_transactions"
   # payment_method_type | character varying(50) | not null  ← column added by v6.0.0 migration
   ```

4. Confirmed v5.9.3 does not populate `payment_method_type` — field introduced in v6.0.0 code

5. Verified no down migration existed
   ```bash
   ls db/migrations/ | grep rollback
   # No results — no down migration provided
   ```

6. Ruled out re-deploying v6.0.0 — root reason for original rollback was unrelated critical bug in reporting path

## Resolution

1. Applied emergency compatibility migration — made column nullable with default
   ```bash
   psql -U postgres -d payments_db -c "
     ALTER TABLE payment_transactions
       ALTER COLUMN payment_method_type DROP NOT NULL,
       ALTER COLUMN payment_method_type SET DEFAULT 'unknown';"
   ```

2. Verified payment writes succeeding immediately
   ```bash
   psql -U postgres -d payments_db -c "
     INSERT INTO payment_transactions (id, user_id, amount) VALUES (gen_random_uuid(), 1, 100.00);"
   # INSERT 0 1 — success
   ```

3. Confirmed error rate dropped to 0% within 90 seconds
   ```bash
   kubectl logs -l app=payment-service -n payments --tail=20
   # No errors
   ```

4. Scheduled proper down migration + v6.1.0 plan for next deploy window

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Rollback causes new failure within 5 min | Page EM + IC immediately | #incident-response |
| DB schema conflict suspected | Engage DBA team | #data-eng |
| Revenue services down >15 min | Executive escalation | PagerDuty P1 policy |

## Post-Incident Notes

**Went well:**
- Root cause identified within 8 min (clear error message, fast DB inspection)
- ALTER TABLE fix applied with zero additional downtime

**Improve:**
- No down migration existed — migration strategy policy not enforced
- Rollback checklist did not mention DB migration state
- The original v6.0.0 deploy was not backward compatible by design

**Action items:**
- [x] Applied compatibility migration, restored payment writes
- [ ] Mandate backward-compatible migrations for all schema changes (expand-then-contract pattern)
- [ ] Add DB migration state check to rollback runbook
- [ ] Require down migration for every up migration in PR checklist
- [ ] Add post-rollback smoke test to deployment pipeline that validates DB writes

## Related Runbooks

- [[RB-005-failed-deployment]]
- [[RB-004-db-timeouts]]
