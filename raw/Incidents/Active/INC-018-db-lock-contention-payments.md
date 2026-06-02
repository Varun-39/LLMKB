---
id: INC-018
title: DB Lock Contention on payments Table — Stalled Writes
severity: SEV-1
service: payment-service
environment: prod
category: degradation
status: resolved
owner: Priya Sharma
assigned-to: Priya Sharma
date: 2026-03-05
duration: 23 minutes
created: 2026-03-05
updated: 2026-03-05
tags:
  - incident
  - database
  - postgres
  - lock-contention
  - critical
  - prod
  - payments
related_runbooks:
  - "[[RB-004-db-timeouts]]"
related_incidents:
  - "[[INC-008-db-timeout-auth-db]]"
  - "[[INC-011-rollback-failed-frontend]]"
---

# INC-018 — DB Lock Contention on payments Table: Stalled Writes

## Summary

At 19:22 UTC on 2026-03-05, payment-service write throughput dropped to near-zero as an ALTER TABLE migration run by a developer held an exclusive lock on the `payment_transactions` table for 21 minutes. The migration was not time-windowed and ran during peak evening traffic. INSERT and UPDATE operations queued behind the lock, exhausting the application connection pool. Service recovered fully once the migration completed and the lock was released.

## Symptoms

- PagerDuty: `PaymentService-WriteLatencyHigh` at 19:24 UTC
- payment-service logs: `ERROR: canceling statement due to lock timeout after 10000ms` — 100% of write operations
- Grafana: payment write P99 latency 90 ms → 45 s
- Payment success rate: dropped from 99.6% to 2% within 2 minutes
- Postgres `pg_stat_activity`: 280 connections in `lock wait` state on `payment_transactions`
- HikariCP: `Connection is not available, request timed out after 30000ms`

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All users attempting to make payments (~7,400 attempts in 23 min) |
| Services degraded | payment-service (writes fully blocked), checkout-service (cascading failure) |
| Revenue impact | ~$61K in blocked payment attempts (most retried post-recovery) |
| Duration | 19:22 → 19:45 UTC (23 min) |
| Data loss | None — all writes rejected cleanly by lock timeout |

## Possible Causes

1. **Unscheduled ALTER TABLE during peak hours** — `ALTER TABLE payment_transactions ADD COLUMN processor_fee NUMERIC(10,4)` held `AccessExclusiveLock`
2. **Migration not using non-blocking DDL** — did not use `ALTER TABLE ... ADD COLUMN ... DEFAULT NULL` (which is instant in Postgres 11+)
3. **No migration time window policy** — no enforcement that DDL migrations run in off-hours maintenance windows
4. **Lock timeout not set on migration session** — migration ran with default `lock_timeout = 0` (infinite wait)

## Troubleshooting Steps

1. Identified lock waiter chain
   ```bash
   psql -U postgres -d payments_db -c "
     SELECT pid, usename, state, wait_event_type, wait_event, query
     FROM pg_stat_activity
     WHERE wait_event_type = 'Lock'
     ORDER BY query_start LIMIT 10;"
   # 280 rows — all waiting on relation lock for payment_transactions
   ```

2. Found the lock holder
   ```bash
   psql -U postgres -d payments_db -c "
     SELECT pid, usename, query_start, query
     FROM pg_stat_activity
     WHERE state = 'active' AND query LIKE '%ALTER TABLE%';"
   # pid: 44221  query: ALTER TABLE payment_transactions ADD COLUMN processor_fee NUMERIC(10,4)
   # Running since 19:21:52 UTC — 3 min at time of check
   ```

3. Checked if migration could be cancelled safely
   ```bash
   psql -U postgres -d payments_db -c "
     SELECT locktype, mode, granted FROM pg_locks WHERE pid = 44221;"
   # relation | AccessExclusiveLock | true — migration was in progress, cancellation safe
   ```

4. Verified application connection pool state
   ```bash
   kubectl logs -l app=payment-service -n payments --tail=30 \
     | grep "Connection is not available"
   # Continuous stream — pool fully exhausted
   ```

## Resolution

1. Cancelled the blocking migration after confirming it was safe to abort
   ```bash
   psql -U postgres -c "SELECT pg_cancel_backend(44221);"
   # PG_CANCEL_BACKEND → t
   ```

2. Lock released — queued connections drained within 45 seconds
   ```bash
   psql -U postgres -d payments_db -c "
     SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock';"
   # 0 — all locks cleared
   ```

3. Confirmed payment write success rate returned to 99.6%

4. Re-ran migration at 02:00 UTC next day using non-blocking approach
   ```sql
   -- Non-blocking: add nullable column first, backfill, then add constraint
   ALTER TABLE payment_transactions ADD COLUMN processor_fee NUMERIC(10,4);
   -- No lock held for add nullable column in PG11+
   ```

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Payments failing >2% for >5 min | Page on-call SRE + DBA | PagerDuty |
| Lock holder identified but running >10 min | Cancel backend with DBA approval | #data-eng |
| Revenue impact >$10K estimated | Page EM + IC | #incident-response |

## Post-Incident Notes

**Went well:**
- Lock holder identified in under 3 minutes using `pg_stat_activity`
- Cancelling the backend was low-risk — migration was additive, not destructive

**Improve:**
- No policy preventing DDL during peak hours (17:00–23:00 UTC)
- Developer had direct prod DB access without a change control gate
- Migration was blocking when a non-blocking equivalent was available

**Action items:**
- [x] Cancelled lock holder, service recovered
- [x] Re-ran migration off-hours using non-blocking DDL
- [ ] Implement `lock_timeout = 3s` for all migration sessions in prod
- [ ] Block direct prod DB access for non-DBA engineers
- [ ] Document non-blocking DDL patterns (expand-contract) in migration runbook

## Related Runbooks

- [[RB-004-db-timeouts]]
