---
id: INC-009
title: DB Connection Pool Exhausted — reporting-service Leak
severity: SEV-2
service: reporting-service
environment: prod
category: degradation
date: 2026-04-24
duration: "47m"
detection_gap: "2m"
tags:
  - incident
  - database
  - connection-pool
  - postgres
  - high
  - prod
  - reporting
---

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
| SLA breach | No — internal service, no external SLA |
| Customer comms | N/A — internal tooling |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 14:50 | Connection pool exhausted; queries begin timing out |
| 14:52 | Alert fired: `ReportingDB-ConnectionPoolExhausted` |
| 14:53 | On-call acknowledged (James Okafor) |
| 15:00 | Leak identified via `pg_stat_activity` — 142 idle connections held >60 min |
| 15:05 | Idle connections terminated on DB |
| 15:10 | reporting-service restarted to flush internal pool |
| 15:25 | Hotfix v2.9.1 deployed with `finally` block fix |
| 15:30 | PgBouncer switched to transaction mode |
| 15:37 | Connection count stable at ~25, incident closed |

## Diagnosis

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

1. **Mitigate:** Terminated leaking connections on DB to restore pool availability
   ```bash
   psql -U postgres -c "
     SELECT pg_terminate_backend(pid)
     FROM pg_stat_activity
     WHERE state = 'idle'
       AND application_name = 'reporting-service'
       AND now() - state_change > interval '60 minutes';"
   # ~142 connections freed
   ```

2. **Fix:** Restarted reporting-service and deployed hotfix v2.9.1 with `finally` block
   ```bash
   kubectl rollout restart deployment/reporting-service -n reporting
   kubectl set image deployment/reporting-service -n reporting \
     reporting-service=registry.internal/reporting-service:v2.9.1
   ```

3. **Verify:** Confirmed connection count stable at ~25 post-fix
   ```bash
   psql -U postgres -c "SELECT count(*) FROM pg_stat_activity WHERE datname='reporting_db';"
   # 23
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Connections >90% of max and rising | Page DBA immediately | PagerDuty |
| Other services degraded due to connection saturation | Escalate to senior on-call + EM | #incident-response |
| Cannot identify leak source in 20 min | Kill all idle connections, restart service | #incident-response |

## Post-Incident Review

**What went well:**
- pg_stat_activity made leak identification fast and unambiguous
- Terminating idle connections provided immediate relief without data risk

**What needs improvement:**
- No connection pool usage alert before exhaustion
- Code review missed missing `finally` block in async path
- PgBouncer was in session mode for a service that doesn't need session-level state

**Contributing factors (beyond root cause):**
- `ExportJobExecutor.java` missing `finally { conn.close(); }` in async path (v2.9.0)
- PgBouncer in session mode held connections per session unnecessarily
- No idle connection reaper configured in HikariCP

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Deploy v2.9.1 hotfix with proper connection cleanup | James Okafor | 2026-04-24 | Done |
| Switch PgBouncer to transaction mode | James Okafor | 2026-04-24 | Done |
| Add alert: connection pool utilization >70% | SRE team | 2026-05-08 | Open |
| Add static analysis check for missing connection cleanup in async paths | Platform team | 2026-05-08 | Open |
| Add idle connection reaper to HikariCP config (idleTimeout=600000) | James Okafor | 2026-05-08 | Open |

## Links

- Runbooks: [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-006-disk-full-db-volume]]
- PR/commit: v2.9.1 hotfix + PR #2301 (PgBouncer config)
- Post-mortem doc: N/A
