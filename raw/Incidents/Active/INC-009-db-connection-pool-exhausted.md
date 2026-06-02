---
id: INC-009
title: DB Connection Pool Exhausted — reporting-service Leak
severity: SEV-2
service: reporting-service
environment: prod
category: degradation
status: resolved
owner: James Okafor
assigned-to: James Okafor
date: 2026-04-24
duration: 47 minutes
created: 2026-04-24
updated: 2026-04-24
tags:
  - incident
  - database
  - connection-pool
  - postgres
  - high
  - prod
  - reporting
related_runbooks:
  - "[[RB-004-db-timeouts]]"
related_incidents: []
---

# INC-009 — DB Connection Pool Exhausted: reporting-service Leak

## Summary

At 14:50 UTC on 2026-04-24, reporting-service exhausted the Postgres connection pool for `reporting-db`, eventually consuming all 200 max_connections on the database server. Connections leaked because a new async export job in v2.9.0 was not releasing pooled connections on exception paths. All reporting queries began queuing and timing out, and the spillover of connection attempts caused brief degradation in auth-service which shares the same Postgres instance on a separate database.

## Symptoms

- PagerDuty: `ReportingDB-ConnectionPoolExhausted` at 14:52 UTC
- reporting-service: `HikariPool-1 - Connection is not available, request timed out after 30000ms`
- Postgres: `FATAL: remaining connection slots are reserved for non-replication superuser connections`
- Grafana: active Postgres connections at 200/200 (max_connections)
- auth-service (same host, different DB): elevated latency due to connection contention
- `/reports/export` endpoint returning HTTP 503 for all users

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All reporting-service users (~340 internal finance/ops users) |
| Services degraded | reporting-service (down), auth-service (mildly degraded — same Postgres host) |
| Revenue impact | None directly — internal tooling |
| Duration | 14:50 → 15:37 UTC (47 min) |
| Data loss | None — queued jobs retained, reprocessed post-recovery |

## Possible Causes

1. **Connection leak on exception path** — async export jobs not calling `connection.close()` in `finally` block when exceptions thrown
2. **Pool max-size too small** — HikariCP pool set to 20 connections for a service with up to 80 concurrent export workers
3. **Long-running queries holding connections** — large exports running >10 min each, exhausting pool under concurrent use
4. **PgBouncer misconfigured** — PgBouncer pool mode set to `session` instead of `transaction`, holding connections per session

## Troubleshooting Steps

1. Confirmed connection pool exhaustion on app side
   ```bash
   kubectl logs -l app=reporting-service -n reporting --tail=100 \
     | grep "Connection is not available"
   # Multiple instances per second
   ```

2. Checked active connections on Postgres
   ```bash
   psql -U postgres -c "
     SELECT count(*), state, wait_event_type, wait_event
     FROM pg_stat_activity
     GROUP BY state, wait_event_type, wait_event
     ORDER BY count DESC;"
   # 198 connections: 142 idle, 56 active on reporting_db
   ```

3. Identified leaking connections — idle connections held >60 min
   ```bash
   psql -U postgres -c "
     SELECT pid, usename, application_name, state,
       now() - state_change AS idle_duration
     FROM pg_stat_activity
     WHERE state = 'idle' AND now() - state_change > interval '60 minutes'
     ORDER BY idle_duration DESC;"
   # 142 rows from reporting-service, idle 90–140 min
   ```

4. Terminated idle connections to provide immediate relief
   ```bash
   psql -U postgres -c "
     SELECT pg_terminate_backend(pid)
     FROM pg_stat_activity
     WHERE state = 'idle'
       AND application_name = 'reporting-service'
       AND now() - state_change > interval '60 minutes';"
   ```

5. Confirmed leak in code — `ExportJobExecutor.java` missing `finally { conn.close(); }` in async path (introduced v2.9.0)

## Resolution

1. Terminated leaking connections on DB to restore pool availability
   ```bash
   # (commands above — ~142 connections freed)
   ```

2. Restarted reporting-service to flush internal pool state
   ```bash
   kubectl rollout restart deployment/reporting-service -n reporting
   ```

3. Deployed hotfix v2.9.1 with `finally` block added to all async job connection paths
   ```bash
   kubectl set image deployment/reporting-service -n reporting \
     reporting-service=registry.internal/reporting-service:v2.9.1
   ```

4. Tuned PgBouncer to `transaction` pool mode for reporting-db (PR #2301)

5. Confirmed connection count stable at ~25 post-fix
   ```bash
   psql -U postgres -c "SELECT count(*) FROM pg_stat_activity WHERE datname='reporting_db';"
   # 23
   ```

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Connections >90% of max and rising | Page DBA immediately | PagerDuty |
| Other services degraded due to connection saturation | Escalate to senior on-call + EM | #incident-response |
| Cannot identify leak source in 20 min | Kill all idle connections, restart service | #incident-response |

## Post-Incident Notes

**Went well:**
- pg_stat_activity made leak identification fast and unambiguous
- Terminating idle connections provided immediate relief without data risk

**Improve:**
- No connection pool usage alert before exhaustion
- Code review missed missing `finally` block in async path
- PgBouncer was in session mode for a service that doesn't need session-level state

**Action items:**
- [x] Deployed v2.9.1 hotfix with proper connection cleanup
- [x] Switched PgBouncer to transaction mode
- [ ] Add alert: connection pool utilization >70%
- [ ] Add static analysis check for missing connection cleanup in async paths
- [ ] Add idle connection reaper to HikariCP config (`idleTimeout=600000`)

## Related Runbooks

- [[RB-004-db-timeouts]]
