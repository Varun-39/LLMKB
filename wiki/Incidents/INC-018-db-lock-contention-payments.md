---
id: INC-018
title: DB Lock Contention on payments Table — Stalled Writes
severity: SEV-1
service: payment-service
environment: prod
category: degradation
date: 2026-03-05
duration: "23m"
detection_gap: "2m"
tags:
  - incident
  - database
  - postgres
  - lock-contention
  - critical
  - prod
  - payments
error_family: connection-pool-exhausted
resolution_runbook: RB-005
resolution_outcome: resolved
---

## Summary

At 19:22 UTC on 2026-03-05, payment-service write throughput dropped to near-zero as an ALTER TABLE migration run by a developer held an exclusive lock on the `payment_transactions` table for 21 minutes during peak evening traffic. INSERT and UPDATE operations queued behind the lock, exhausting the connection pool. Service recovered once the migration was cancelled.

## Symptoms

- PagerDuty: `PaymentService-WriteLatencyHigh` fired at 19:24 UTC
- payment-service logs: `ERROR: canceling statement due to lock timeout after 10000ms` on 100% of writes
- Grafana: payment write P99 latency 90 ms → 45 s
- Payment success rate: dropped from 99.6% to 2% within 2 minutes
- `pg_stat_activity`: 280 connections in `lock wait` state on `payment_transactions`
- HikariCP: `Connection is not available, request timed out after 30000ms`

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All users attempting payments (~7,400 attempts in 23 min) |
| Services degraded | payment-service (writes fully blocked), checkout-service (cascading failure) |
| Revenue impact | ~$61K in blocked payment attempts (most retried post-recovery) |
| Duration | 19:22 → 19:45 UTC (23 min) |
| Data loss | None — all writes rejected cleanly by lock timeout |
| SLA breach | Yes — payments SLA (99.95% uptime) breached |
| Customer comms | Status page updated at 19:28 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 19:21 | Developer ran `ALTER TABLE payment_transactions ADD COLUMN processor_fee ...` in prod |
| 19:22 | AccessExclusiveLock acquired; application writes began queuing |
| 19:24 | Alert fired |
| 19:25 | On-call acknowledged (Priya Sharma) |
| 19:28 | Lock holder identified via `pg_stat_activity` |
| 19:30 | Decision: cancel the migration backend |
| 19:31 | `pg_cancel_backend` executed, lock released |
| 19:32 | Queued connections drained, writes resumed |
| 19:45 | Full recovery confirmed, incident closed |

## Diagnosis

1. Identified lock waiter chain
   ```bash
   psql -U postgres -d payments_db -c "
     SELECT pid, usename, state, wait_event_type, wait_event, query
     FROM pg_stat_activity
     WHERE wait_event_type = 'Lock'
     ORDER BY query_start LIMIT 10;"
   # 280 rows — all waiting on relation lock for payment_transactions
   ```

2. Found the lock holder — ALTER TABLE running since 19:21
   ```bash
   psql -U postgres -d payments_db -c "
     SELECT pid, usename, query_start, query
     FROM pg_stat_activity
     WHERE state = 'active' AND query LIKE '%ALTER TABLE%';"
   # pid: 44221  query: ALTER TABLE payment_transactions ADD COLUMN processor_fee NUMERIC(10,4)
   # Running since 19:21:52 UTC
   ```

3. Confirmed lock type and that cancellation was safe
   ```bash
   psql -U postgres -d payments_db -c "
     SELECT locktype, mode, granted FROM pg_locks WHERE pid = 44221;"
   # relation | AccessExclusiveLock | true — additive migration, safe to cancel
   ```

## Resolution

1. **Mitigate:** Cancelled the blocking migration
   ```bash
   psql -U postgres -c "SELECT pg_cancel_backend(44221);"
   # pg_cancel_backend → t
   ```

2. **Fix:** Re-ran migration at 02:00 UTC next day using non-blocking approach
   ```sql
   -- Non-blocking: add nullable column (instant in PG11+)
   ALTER TABLE payment_transactions ADD COLUMN processor_fee NUMERIC(10,4);
   ```

3. **Verify:** Confirmed lock cleared and payment success rate restored
   ```bash
   psql -U postgres -d payments_db -c "
     SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock';"
   # 0 — all locks cleared
   # Grafana: payment success rate 99.6% within 90 seconds
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Payments failing >2% for >5 min | Page on-call SRE + DBA | PagerDuty |
| Lock holder identified but running >10 min | Cancel backend with DBA approval | #data-eng |
| Revenue impact >$10K estimated | Page EM + IC | #incident-response |

## Post-Incident Review

**What went well:**
- Lock holder identified in under 3 minutes using `pg_stat_activity`
- Cancelling the backend was low-risk — migration was additive, not destructive

**What needs improvement:**
- No policy preventing DDL during peak hours (17:00–23:00 UTC)
- Developer had direct prod DB access without a change control gate
- Migration was blocking when a non-blocking equivalent was available

**Contributing factors (beyond root cause):**
- No `lock_timeout` configured on migration sessions (default = infinite)
- Lack of documented non-blocking DDL patterns for the team
- No runbook for handling lock contention emergencies

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Implement `lock_timeout = 3s` for all migration sessions in prod | DBA team | 2026-03-19 | Open |
| Block direct prod DB access for non-DBA engineers | Platform team | 2026-03-19 | Open |
| Document non-blocking DDL patterns (expand-contract) in migration runbook | Priya Sharma | 2026-03-26 | Open |
| Add peak-hours DDL policy to deployment guidelines | SRE team | 2026-03-26 | Open |

## Links

- Runbooks: [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-008-db-timeout-auth-db]], [[INC-011-rollback-failed-frontend]]
- PR/commit: N/A
- Post-mortem doc: N/A
