---
id: INC-017
title: Postgres Read Replica Lag — Reporting Queries Returning Stale Data
severity: SEV-2
service: reporting-service
environment: prod
category: degradation
date: 2026-03-11
duration: "1h 8m"
detection_gap: "2m"
tags:
  - incident
  - database
  - postgres
  - replication
  - replica-lag
  - high
  - prod
  - reporting
error_family: db-read-replica-lag
resolution_runbook: RB-005
resolution_outcome: resolved
---

## Summary

At 14:00 UTC on 2026-03-11, the `reporting-db` read replica fell approximately 45 minutes behind the primary due to a large one-off data backfill operation being run against the primary during business hours. Reporting-service queries were routed to the replica and returned data up to 45 minutes stale. Finance users noticed incorrect report totals. Replica caught up after the backfill completed and read traffic was momentarily drained from it.

## Symptoms

- Finance team alert: "Dashboard totals don't match — showing data from 45 min ago" (09:00 UTC report window)
- `pg_stat_replication` on primary: replica lag at 2.7 GB and growing at 14:05 UTC
- Datadog: `reporting_db.replica_lag_bytes` alert at 14:02 UTC (threshold: 500 MB)
- WAL sender on primary consuming 80% of primary disk I/O
- `SHOW synchronous_commit` on replica: `off` — async replication confirmed

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~85 internal finance and ops users |
| Services degraded | reporting-service (stale data on all read queries) |
| Revenue impact | None directly; incorrect reports caused manual reconciliation effort (~4 hours) |
| Duration | 13:20 → 15:28 UTC (68 min of actionable lag) |
| Data loss | None — data existed on primary, replica caught up fully |
| SLA breach | No — internal reporting, no external SLA |
| Customer comms | N/A — internal tooling |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 13:08 | Backfill job started: `UPDATE orders SET legacy_id = ...` (18M rows) |
| 13:20 | Replica lag exceeds 5 min (not yet detected) |
| 14:02 | Alert fired: `reporting_db.replica_lag_bytes` exceeded 500 MB |
| 14:03 | On-call acknowledged (James Okafor) |
| 14:10 | Confirmed replica 47 min behind primary |
| 14:15 | Reporting reads redirected to primary |
| 14:20 | Backfill job cancelled (rescheduled off-hours) |
| 15:10 | Replica lag recovered to <1 sec |
| 15:20 | Reporting reads re-routed back to replica |
| 15:28 | Incident closed |

## Diagnosis

1. Confirmed replica lag on primary
   ```bash
   psql -U postgres -c "
     SELECT client_addr,
       pg_size_pretty(sent_lsn - write_lsn) AS write_lag,
       pg_size_pretty(sent_lsn - flush_lsn) AS flush_lag,
       pg_size_pretty(sent_lsn - replay_lsn) AS replay_lag
     FROM pg_stat_replication;"
   # replica: replay_lag = 2.7 GB
   ```

2. Identified the source of WAL generation
   ```bash
   psql -U postgres -c "
     SELECT pid, query_start, state, query
     FROM pg_stat_activity
     WHERE state = 'active'
     ORDER BY query_start LIMIT 5;"
   # Long-running: UPDATE orders SET legacy_id = gen_legacy_id(id) WHERE legacy_id IS NULL
   # Running since 13:08 UTC — 18M rows affected so far
   ```

3. Checked replica apply rate
   ```bash
   # On replica:
   psql -U replication_user -c "SELECT now() - pg_last_xact_replay_timestamp() AS lag;"
   # 00:47:23 — 47 minutes behind
   ```

4. Verified reporting-service was hitting the replica (not primary)
   ```bash
   psql -U postgres -d reporting_db -c "SELECT inet_server_addr();"
   # 10.0.3.45  ← confirmed replica IP
   ```

## Resolution

1. **Mitigate:** Temporarily redirected reporting-service reads to primary
   ```bash
   kubectl set env deployment/reporting-service -n reporting \
     DB_READ_HOST=db-primary-01.internal
   kubectl rollout restart deployment/reporting-service -n reporting
   ```

2. **Fix:** Killed the backfill job to stop WAL generation (rescheduled to off-hours)
   ```bash
   psql -U postgres -c "SELECT pg_cancel_backend(<backfill-pid>);"
   ```

3. **Verify:** Monitored replica lag — recovered from 47 min to <1 sec within 18 min; re-routed reads back to replica
   ```bash
   kubectl set env deployment/reporting-service -n reporting \
     DB_READ_HOST=db-replica-01.internal
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Replica lag >5 min in prod | Alert DBA + on-call SRE | PagerDuty |
| Stale data reported by users | Immediately switch reads to primary | #incident-response |
| Replica cannot catch up within 30 min | Assess whether replica needs promotion | #data-eng |

## Post-Incident Review

**What went well:**
- Switching reads to primary was fast and immediately resolved user-visible stale data
- Replica caught up cleanly once backfill was cancelled

**What needs improvement:**
- Backfill ran during business hours without capacity planning review
- Reporting-service had no automatic fallback when replica lag exceeded threshold
- Lag alert existed but wasn't acknowledged in on-call runbook

**Contributing factors (beyond root cause):**
- Backfill of 18M rows generated massive WAL volume during business hours
- Replica running on smaller instance class (`db.r6g.large` vs. primary `db.r6g.2xlarge`)
- No automatic lag-based read routing in reporting-service

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Reroute reads to primary, cancel backfill | James Okafor | 2026-03-11 | Done |
| Add automatic lag-based read routing to reporting-service (fallback to primary if lag >30 sec) | James Okafor | 2026-03-25 | Open |
| Require off-hours scheduling + DBA sign-off for any bulk write operation >1M rows | DBA team | 2026-03-25 | Open |
| Upgrade read replica to match primary instance class | Platform team | 2026-04-01 | Open |

## Links

- Runbooks: [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-009-db-connection-pool-exhausted]], [[INC-006-disk-full-db-volume]]
- PR/commit: N/A
- Post-mortem doc: N/A
