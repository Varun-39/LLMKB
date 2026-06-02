---
id: INC-008
title: DB Timeout on auth-db — Missing Index After Migration
severity: SEV-2
service: auth-service
environment: prod
category: degradation
status: resolved
owner: Sara Ndiaye
assigned-to: Sara Ndiaye
date: 2026-04-30
duration: 55 minutes
created: 2026-04-30
updated: 2026-04-30
tags:
  - incident
  - database
  - timeout
  - postgres
  - high
  - prod
  - auth
related_runbooks:
  - "[[RB-004-db-timeouts]]"
related_incidents:
  - "[[INC-006-disk-full-db-volume]]"
---

# INC-008 — DB Timeout on auth-db: Missing Index After Migration

## Summary

At 10:12 UTC on 2026-04-30, auth-service began returning elevated 504 errors following a database schema migration that inadvertently dropped the index on `sessions.user_id`. Sequential scans on the 80M-row sessions table caused query times to jump from <5 ms to 8–14 s, exceeding the auth-service's 10 s query timeout. ~15% of login attempts failed during the 55-minute window until the index was recreated concurrently.

## Symptoms

- Datadog: auth-service DB query P99 latency jumped from 4 ms to 12 s at 10:12 UTC
- PagerDuty: `AuthService-DBTimeout` at 10:14 UTC
- ~15% of login attempts failing with HTTP 500 (`query timeout after 10000ms`)
- auth-service error logs: `ERROR: canceling statement due to statement timeout`
- Postgres `pg_stat_activity`: dozens of queries in `active` state for >10 s on `sessions` table
- Grafana: DB connection pool utilization at 95% (connections held by slow queries)

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~15% of login attempts (~2,100 users in 55 min window) |
| Services degraded | auth-service (login degraded), api-gateway (downstream auth checks slow) |
| Revenue impact | ~$5K in lost conversions from failed logins |
| Duration | 10:12 → 11:07 UTC (55 min) |
| Data loss | None |

## Possible Causes

1. **Migration dropped index** — `ALTER TABLE sessions DROP COLUMN legacy_token` migration also removed composite index `idx_sessions_user_id_created`
2. **Autovacuum running** — post-migration autovacuum causing temporary I/O saturation
3. **Traffic spike** — higher than normal morning login surge overwhelming a degraded table
4. **Connection pool misconfigured** — pool too small for degraded query latency profile

## Troubleshooting Steps

1. Confirmed slow queries on sessions table
   ```bash
   psql -U postgres -d auth_db -c "
     SELECT pid, now() - query_start AS duration, query
     FROM pg_stat_activity
     WHERE state = 'active' AND now() - query_start > interval '5 seconds'
     ORDER BY duration DESC LIMIT 10;"
   # All slow queries: SELECT ... FROM sessions WHERE user_id = $1
   ```

2. Checked existing indexes on sessions table
   ```bash
   psql -U postgres -d auth_db -c "\d sessions"
   # No index on user_id column — previously had idx_sessions_user_id_created
   ```

3. Explained query plan to confirm sequential scan
   ```bash
   psql -U postgres -d auth_db -c "
     EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM sessions WHERE user_id = 12345 LIMIT 1;"
   # Seq Scan on sessions (cost=0.00..4823091.00) rows=80,411,203
   # Planning time: 0.4 ms  Execution time: 13,842 ms
   ```

4. Correlated with migration run at 10:08 UTC — migration `20260430_drop_legacy_token.sql` confirmed dropped composite index

## Resolution

1. Recreated index concurrently (no table lock, zero downtime)
   ```bash
   psql -U postgres -d auth_db -c "
     CREATE INDEX CONCURRENTLY idx_sessions_user_id_created
     ON sessions (user_id, created_at DESC);"
   # Index build time: ~18 min (80M rows)
   ```

2. Monitored query latency during index build — queries improved progressively as index was usable

3. Confirmed query plan using index
   ```bash
   psql -U postgres -d auth_db -c "
     EXPLAIN (ANALYZE) SELECT * FROM sessions WHERE user_id = 12345 LIMIT 1;"
   # Index Scan using idx_sessions_user_id_created
   # Execution time: 0.8 ms
   ```

4. Confirmed error rate dropped to 0% and auth-service latency normalized

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Login failure rate >5% after 10 min | Escalate to DBA + senior on-call | PagerDuty |
| Cannot identify or fix DB issue in 20 min | Page EM, evaluate read replica failover | #incident-response |
| Index build failing or DB under heavy load | Engage DBA team | #data-eng |

## Post-Incident Notes

**Went well:**
- `CREATE INDEX CONCURRENTLY` allowed recovery with no additional downtime
- Slow query detection in pg_stat_activity was fast and decisive

**Improve:**
- Migration script did not include a check to preserve dependent indexes
- No staging replay of migration on production-scale data volume
- Index health not monitored — no alert when expected indexes are missing

**Action items:**
- [x] Recreated sessions index concurrently
- [ ] Add post-migration validation step: check expected indexes exist
- [ ] Run migrations against staging DB with prod-scale data clone before prod
- [ ] Add pg_indexes monitoring for critical tables

## Related Runbooks

- [[RB-004-db-timeouts]]
