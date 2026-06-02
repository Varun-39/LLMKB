---
id: INC-017
title: Postgres Read Replica Lag — Reporting Queries Returning Stale Data
severity: SEV-2
service: reporting-service
environment: prod
category: degradation
status: resolved
owner: James Okafor
assigned-to: James Okafor
date: 2026-03-11
duration: 68 minutes
created: 2026-03-11
updated: 2026-03-11
tags:
  - incident
  - database
  - postgres
  - replication
  - replica-lag
  - high
  - prod
  - reporting
related_runbooks:
  - "[[RB-004-db-timeouts]]"
related_incidents:
  - "[[INC-009-db-connection-pool-exhausted]]"
  - "[[INC-006-disk-full-db-volume]]"
---

# INC-017 — Postgres Read Replica Lag: Reporting Queries Returning Stale Data

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
| Duration | ~13:20 → 15:28 UTC (68 min of actionable lag) |
| Data loss | None — data existed on primary, replica caught up fully |

## Possible Causes

1. **Backfill running during business hours** — `UPDATE orders SET legacy_id = ...` batch processing 18M rows on primary, generating huge WAL volume
2. **Replica under-resourced** — replica running on `db.r6g.large` vs. primary `db.r6g.2xlarge`, unable to apply WAL fast enough
3. **No read replica lag alerting** — threshold was set but not acknowledged in on-call setup
4. **Reporting queries not replica-aware** — no fallback to primary when replica lag exceeds threshold

## Troubleshooting Steps

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

1. Temporarily redirected reporting-service reads to primary by updating connection string
   ```bash
   kubectl set env deployment/reporting-service -n reporting \
     DB_READ_HOST=db-primary-01.internal
   kubectl rollout restart deployment/reporting-service -n reporting
   ```

2. Killed the backfill job to stop WAL generation (job rescheduled off-hours)
   ```bash
   psql -U postgres -c "SELECT pg_cancel_backend(<backfill-pid>);"
   ```

3. Monitored replica lag — recovered from 47 min to <1 sec within 18 min

4. Re-routed reporting reads back to replica once lag < 10 sec
   ```bash
   kubectl set env deployment/reporting-service -n reporting \
     DB_READ_HOST=db-replica-01.internal
   ```

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Replica lag >5 min in prod | Alert DBA + on-call SRE | PagerDuty |
| Stale data reported by users | Immediately switch reads to primary | #incident-response |
| Replica cannot catch up within 30 min | Assess whether replica needs promotion | #data-eng |

## Post-Incident Notes

**Went well:**
- Switching reads to primary was fast and immediately resolved user-visible stale data
- Replica caught up cleanly once backfill was cancelled

**Improve:**
- Backfill ran during business hours without capacity planning review
- Reporting-service had no automatic fallback when replica lag exceeded threshold
- Lag alert existed but wasn't acknowledged in on-call runbook

**Action items:**
- [x] Rerouted reads to primary, replica recovered
- [ ] Add automatic lag-based read routing to reporting-service (fallback to primary if lag >30 sec)
- [ ] Require off-hours scheduling + DBA sign-off for any bulk write operation >1M rows
- [ ] Upgrade read replica to match primary instance class

## Related Runbooks

- [[RB-004-db-timeouts]]
