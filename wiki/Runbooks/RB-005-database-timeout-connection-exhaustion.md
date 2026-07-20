---
id: RB-005
title: Database Timeout and Connection Exhaustion
service: postgres-primary
related_services:
  - auth-service
  - payment-service
  - reporting-service
  - pgbouncer
severity: SEV-2
environment: prod
category: connectivity
risk_level: high
estimated_duration: "25m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - database
  - postgres
  - timeout
  - connection-pool
  - prod
related_incidents:
  - "[[INC-008-db-timeout-auth-db]]"
  - "[[INC-009-db-connection-pool-exhausted]]"
  - "[[INC-017-db-read-replica-lag]]"
  - "[[INC-018-db-lock-contention-payments]]"
related_runbooks:
  - "[[RB-003-disk-space-full]]"
related_guardrails: []
---

## Purpose

Diagnose and resolve database timeouts and connection pool exhaustion for Postgres services, covering connection leaks, lock contention, missing indexes, and replica lag.

**Desired outcome:** Query latency at baseline (<10ms P95 for reads), connection pool utilization below 70%, no timeout errors.

## Success Criteria

Before closing the incident or declaring the runbook complete, ALL of the following must be true:

- `pg_stat_activity` shows connection count well below `max_connections`
- No queries running longer than 5 seconds
- No lock waits visible in `pg_locks`
- Application timeout error rate returned to 0%
- Connection pool metrics on Grafana stable below 70% utilization

## Scope

| Attribute | Value |
|-----------|-------|
| Service | postgres-primary |
| Related services | auth-service, payment-service, reporting-service, pgbouncer |
| Environments | prod, staging |
| Use when | `*-DBTimeout`, `*-ConnectionPoolExhausted`, or `*-SlowQueries` alert |
| Do NOT use when | Database is unreachable (network issue — check connectivity first) |
| Risk level | High (killing connections can cause data inconsistency) |
| Estimated duration | 20–25 minutes |
| Approval required | No (but DBA approval needed for killing connections or dropping slots) |

## Prerequisites

- [ ] `psql` access to affected database (superuser credentials for diagnostic queries)
- [ ] Grafana access to DB dashboards (connections, query latency, pool stats)
- [ ] Knowledge of which application is affected and which database it connects to
- [ ] DBA team contact information (for destructive operations like killing connections)

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `psql` | Database diagnostics and mitigation | Superuser |
| `kubectl` | Application-side logs and restarts | Cluster admin |
| Grafana | Connection pool and query latency metrics | Read access |
| PgBouncer admin console | Connection pooler diagnostics | Admin access |

## Trigger

- Alert: `*-DBTimeout`, `*-ConnectionPoolExhausted`, or `*-SlowQueries`
- Symptom: Application logs `query timeout after 10000ms` or `Connection is not available after 30000ms`
- Symptom: Postgres logs `FATAL: remaining connection slots are reserved for non-replication superuser connections`
- Metric: Connection pool utilization >90% or query P99 latency spike on Grafana

## Triage

1. Check active connection count vs. max
   ```bash
   psql -U postgres -c "
     SELECT count(*) AS total,
       count(*) FILTER (WHERE state = 'active') AS active,
       count(*) FILTER (WHERE state = 'idle') AS idle,
       count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx
     FROM pg_stat_activity;"
   psql -U postgres -c "SHOW max_connections;"
   # What to look for: total ≈ max_connections = pool exhausted
   ```

2. Assess blast radius — single application or all services timing out
   ```bash
   psql -U postgres -c "
     SELECT application_name, count(*) FROM pg_stat_activity GROUP BY 1 ORDER BY 2 DESC;"
   ```

3. Wrong symptoms? Database unreachable entirely? → Check network/DNS, not this runbook.

## Investigation

1. **Identify long-running or blocked queries**
   ```bash
   psql -U postgres -c "
     SELECT pid, usename, state, wait_event_type, wait_event,
       now() - query_start AS duration, left(query, 80) AS query
     FROM pg_stat_activity
     WHERE state = 'active' AND now() - query_start > interval '5 seconds'
     ORDER BY duration DESC LIMIT 20;"
   ```

2. **Check for lock contention**
   ```bash
   psql -U postgres -c "
     SELECT blocked_locks.pid AS blocked_pid,
       blocking_locks.pid AS blocking_pid,
       blocked_activity.query AS blocked_query,
       blocking_activity.query AS blocking_query
     FROM pg_catalog.pg_locks blocked_locks
     JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
     JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
       AND blocking_locks.relation = blocked_locks.relation
       AND blocking_locks.pid != blocked_locks.pid
     JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
     WHERE NOT blocked_locks.granted
     LIMIT 10;"
   ```

3. **Check for connection leaks (long idle connections)**
   ```bash
   psql -U postgres -c "
     SELECT pid, usename, application_name, state,
       now() - state_change AS idle_duration
     FROM pg_stat_activity
     WHERE state = 'idle' AND now() - state_change > interval '30 minutes'
     ORDER BY idle_duration DESC LIMIT 20;"
   # What to look for: large number of long-idle connections = connection leak
   ```

4. **Check query performance (missing index?)**
   ```bash
   psql -U postgres -d <database> -c "
     EXPLAIN (ANALYZE, BUFFERS) <suspected-slow-query>;"
   # What to look for: Seq Scan on large table = missing index
   ```

5. **Check replica lag** (if reads go to replica)
   ```bash
   psql -U postgres -c "
     SELECT client_addr,
       pg_size_pretty(sent_lsn - replay_lsn) AS replay_lag
     FROM pg_stat_replication;"
   ```

6. **Check application-side connection pool**
   ```bash
   kubectl logs -l app=<service> -n <namespace> --tail=50 | grep -i "hikari\|connection\|pool"
   # What to look for: "Connection is not available", pool stats
   ```

7. **Decision point:**
   - IF long-idle connections from one app → proceed to Mitigation Option A
   - IF lock contention (ALTER TABLE or long tx blocking) → proceed to Mitigation Option B
   - IF missing index causing seq scans → proceed to Mitigation Option C
   - IF replica lag causing stale reads → proceed to Mitigation Option D
   - IF general timeout, no clear cause → proceed to Mitigation Option E
   - IF unclear → escalate (see Escalation section)

## Mitigation

### Option A: Connection pool exhausted by leaking connections

```bash
# Kill idle connections older than 30 min from the offending application:
psql -U postgres -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE state = 'idle'
    AND application_name = '<service-name>'
    AND now() - state_change > interval '30 minutes';"
# Restart the service to flush internal pool state:
kubectl rollout restart deployment/<service> -n <namespace>
```

### Option B: Lock contention (ALTER TABLE or long transaction blocking writes)

```bash
# Cancel the blocking query (non-destructive):
psql -U postgres -c "SELECT pg_cancel_backend(<blocking-pid>);"
# IF pg_cancel doesn't work (DDL in progress):
psql -U postgres -c "SELECT pg_terminate_backend(<blocking-pid>);"
```

### Option C: Missing index causing sequential scans and timeouts

```bash
# Create index concurrently (no table lock):
psql -U postgres -d <database> -c "
  CREATE INDEX CONCURRENTLY idx_<table>_<column>
  ON <table> (<column>);"
# Monitor build progress:
psql -U postgres -c "SELECT * FROM pg_stat_progress_create_index;"
```

### Option D: Replica lag causing stale reads

```bash
# Temporarily redirect reads to primary:
kubectl set env deployment/<service> -n <namespace> DB_READ_HOST=<primary-host>
kubectl rollout restart deployment/<service> -n <namespace>
# Kill backfill or bulk operation causing WAL pressure:
psql -U postgres -c "SELECT pg_cancel_backend(<backfill-pid>);"
```

### Option E: General timeout relief — increase statement timeout temporarily

```bash
kubectl set env deployment/<service> -n <namespace> DB_STATEMENT_TIMEOUT_MS=30000
kubectl rollout restart deployment/<service> -n <namespace>
```

**After mitigation:** Monitor for 10–15 minutes — connection pool below 70%, no timeout errors, query latency at baseline.

## Verification

- [ ] `pg_stat_activity` shows connection count well below `max_connections`
- [ ] No queries running longer than 5 seconds
- [ ] No lock waits visible
- [ ] Application timeout error rate returned to 0%
- [ ] Connection pool metrics on Grafana stable below 70% utilization

```bash
psql -U postgres -c "
  SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '5s';"
# Expected: 0
kubectl logs -l app=<service> -n <namespace> --tail=20 | grep -c "timeout\|not available"
# Expected: 0
```

## Failure Signals

If the mitigation did NOT work, you will observe one or more of the following:

- Connection count climbs back to max_connections within minutes
- Timeout errors continue appearing in application logs
- Lock contention reappears (same or different blocking PID)
- Query latency P99 does not improve
- New services begin experiencing timeouts (spreading issue)

**If any failure signal is present after mitigation:** Do NOT repeat the same step. Proceed to Rollback or Escalation immediately.

## Rollback

1. **If you terminated connections that shouldn't have been killed:**
   ```bash
   kubectl rollout restart deployment/<service> -n <namespace>
   ```

2. **If you redirected reads to primary (Option D):**
   ```bash
   kubectl set env deployment/<service> -n <namespace> DB_READ_HOST=<replica-host>
   kubectl rollout restart deployment/<service> -n <namespace>
   ```

3. **If you increased statement timeout:**
   ```bash
   kubectl set env deployment/<service> -n <namespace> DB_STATEMENT_TIMEOUT_MS=10000
   kubectl rollout restart deployment/<service> -n <namespace>
   ```

4. **If index creation is causing issues:**
   ```bash
   psql -U postgres -d <database> -c "DROP INDEX CONCURRENTLY idx_<table>_<column>;"
   ```

5. Notify #incident-response: "Rollback executed — escalating."

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Cannot identify slow query or lock holder in 15 min | DBA team | #data-eng | 10 min response |
| Connection count at max_connections and rising | DBA + platform team | PagerDuty P1 | Immediate |
| Revenue service timeouts >20 min | Engineering Manager + IC | #incident-response | Immediate |
| Data integrity concern (partial writes, stuck transactions) | DBA team | #data-eng | Immediate |
| Need to kill a production DDL migration | DBA approval required | #data-eng | 5 min response |

## Notes

- **Never kill connections blindly.** Always identify the application first. Killing connections from a critical service mid-transaction can cause data inconsistency.
- **`pg_cancel_backend` vs. `pg_terminate_backend`:** Cancel sends a polite "stop your query" signal. Terminate kills the connection entirely. Prefer cancel first.
- **Connection pool ≠ database connections.** If HikariCP is set to 20 but you see 200 DB connections, something is leaking. See [[INC-009-db-connection-pool-exhausted]].
- **ALTER TABLE during peak traffic** is the #1 cause of lock contention in this environment. See [[INC-018-db-lock-contention-payments]] — always use non-blocking DDL.
- **Missing indexes after migration** can cause latency to jump 1000×. See [[INC-008-db-timeout-auth-db]] — check `\d <table>` to verify expected indexes exist.
- **PgBouncer mode matters:** `session` mode holds connections per session; `transaction` mode releases after each transaction. For connection exhaustion, switching to `transaction` mode often fixes the problem.
- See also: [[INC-008-db-timeout-auth-db]], [[INC-018-db-lock-contention-payments]]

## Maintenance

- **Last tested:** 2026-06-02
- **Review cycle:** Quarterly
- **Next review:** 2026-09-02
- **Test method:** Simulate connection exhaustion by opening max connections from a test client in staging, execute runbook diagnostic and mitigation steps.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-02 | SRE Team + DBA Team | Initial publication |
| 2026-06-12 | SRE Team | Migrated to new runbook template format |
