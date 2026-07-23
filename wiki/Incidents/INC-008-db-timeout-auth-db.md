---
id: INC-008
title: DB Timeout on auth-db — Missing Index After Migration
severity: SEV-2
service: auth-service
environment: prod
category: degradation
date: 2026-04-30
duration: "55m"
detection_gap: "2m"
tags:
  - incident
  - database
  - timeout
  - postgres
  - high
  - prod
  - auth
error_family: connection-pool-exhausted
resolution_runbook: RB-005
resolution_outcome: resolved
---

## Summary

At 10:12 UTC on 2026-04-30, auth-service began returning elevated 504 errors following a database schema migration that inadvertently dropped the index on `sessions.user_id`. Sequential scans on the 80M-row table caused query times to jump from <5 ms to 8–14 s, failing ~15% of login attempts for 55 minutes until the index was recreated concurrently.

## Symptoms

- Datadog: auth-service DB query P99 latency jumped from 4 ms to 12 s at 10:12 UTC
- PagerDuty: `AuthService-DBTimeout` fired at 10:14 UTC
- ~15% of login attempts failing with HTTP 500 (`query timeout after 10000ms`)
- auth-service error logs: `ERROR: canceling statement due to statement timeout`
- `pg_stat_activity`: dozens of queries in `active` state for >10 s on `sessions` table
- Grafana: DB connection pool utilization at 95%

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~2,100 users (15% of login attempts in 55-min window) |
| Services degraded | auth-service (login degraded), api-gateway (downstream auth checks slow) |
| Revenue impact | ~$5K in lost conversions from failed logins |
| Duration | 10:12 → 11:07 UTC (55 min) |
| Data loss | None |
| SLA breach | No — degradation stayed below 99.9% threshold for total outage |
| Customer comms | N/A — partial degradation, no status page update |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 10:08 | Migration `20260430_drop_legacy_token.sql` executed in prod |
| 10:12 | Query latency spike began (index silently dropped) |
| 10:14 | Alert fired |
| 10:15 | On-call acknowledged (Sara Ndiaye) |
| 10:22 | Root cause identified — missing index on sessions.user_id |
| 10:25 | `CREATE INDEX CONCURRENTLY` started |
| 10:43 | Index build completed (18 min for 80M rows) |
| 11:07 | Latency fully normalized, error rate at 0%, incident closed |

## Diagnosis

1. Confirmed slow queries on sessions table
   ```bash
   psql -U postgres -d auth_db -c "
     SELECT pid, now() - query_start AS duration, query
     FROM pg_stat_activity
     WHERE state = 'active' AND now() - query_start > interval '5 seconds'
     ORDER BY duration DESC LIMIT 10;"
   # All slow queries: SELECT ... FROM sessions WHERE user_id = $1
   ```

2. Checked existing indexes — confirmed index was missing
   ```bash
   psql -U postgres -d auth_db -c "\di sessions*"
   # No index on user_id column — idx_sessions_user_id_created gone
   ```

3. Explained query plan to confirm sequential scan
   ```bash
   psql -U postgres -d auth_db -c "
     EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM sessions WHERE user_id = 12345 LIMIT 1;"
   # Seq Scan on sessions (cost=0.00..4823091.00) rows=80,411,203
   # Execution time: 13,842 ms
   ```

4. Correlated with migration at 10:08 UTC — `DROP COLUMN legacy_token` cascade also removed composite index
   ```bash
   grep -i "index" db/migrations/20260430_drop_legacy_token.sql
   # ALTER TABLE sessions DROP COLUMN legacy_token CASCADE;
   ```

## Resolution

1. **Mitigate:** No immediate mitigation available — index rebuild required; increased statement timeout to 30s to reduce error rate during build
   ```bash
   psql -U postgres -d auth_db -c "ALTER SYSTEM SET statement_timeout = '30s';"
   psql -U postgres -d auth_db -c "SELECT pg_reload_conf();"
   ```

2. **Fix:** Recreated index concurrently (no table lock, zero downtime, No write lock)
   ```bash
   psql -U postgres -d auth_db -c "
     CREATE INDEX CONCURRENTLY idx_sessions_user_id_created
     ON sessions (user_id, created_at DESC);"
   # Index build time: ~18 min (80M rows)
   ```

3. **Verify:** Confirmed query plan using index and latency normalized
   ```bash
   psql -U postgres -d auth_db -c "
     EXPLAIN (ANALYZE) SELECT * FROM sessions WHERE user_id = 12345 LIMIT 1;"
   # Index Scan using idx_sessions_user_id_created
   # Execution time: 0.8 ms
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Login failure rate >5% after 10 min | Escalate to DBA + senior on-call | PagerDuty |
| Cannot identify or fix DB issue in 20 min | Page EM, evaluate read replica failover | #incident-response |
| Index build failing or DB under heavy load | Engage DBA team | #data-eng |

## Post-Incident Review

**What went well:**
- `CREATE INDEX CONCURRENTLY` allowed recovery with no additional downtime
- Slow query detection in `pg_stat_activity` was fast and decisive

**What needs improvement:**
- Migration script did not include a check to preserve dependent indexes
- No staging replay of migration on production-scale data volume
- Index health not monitored — no alert when expected indexes are missing

**Contributing factors (beyond root cause):**
- `CASCADE` keyword in migration silently dropped dependent objects
- No automated post-migration index validation in CI/CD pipeline
- Staging DB had only 50K rows — performance degradation not caught

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add post-migration validation step: check expected indexes exist | Sara Ndiaye | 2026-05-14 | Open |
| Run migrations against staging DB with prod-scale data clone before prod | Platform team | 2026-05-21 | Open |
| Add pg_indexes monitoring for critical tables | SRE team | 2026-05-14 | Open |

## Links

- Runbooks: [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-006-disk-full-db-volume]]
- PR/commit: N/A
- Post-mortem doc: N/A
