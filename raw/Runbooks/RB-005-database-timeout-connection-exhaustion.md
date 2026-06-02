<!-- File: RB-005-database-timeout-connection-exhaustion.md -->
---
id: RB-005
title: Database Timeout and Connection Exhaustion
service_scope: auth-service, payment-service, reporting-service
environment_scope: prod, staging
owner: SRE Team + DBA Team
severity_scope: high, critical
tags:
  - runbook
  - database
  - postgres
  - timeout
  - connection-pool
  - prod
created: 2026-06-02
updated: 2026-06-02
related_incidents:
  - "[[INC-008-db-timeout-auth-db]]"
  - "[[INC-009-db-connection-pool-exhausted]]"
  - "[[INC-017-db-read-replica-lag]]"
  - "[[INC-018-db-lock-contention-payments]]"
---

# Database Timeout and Connection Exhaustion

## Trigger

- PagerDuty alert: `*-DBTimeout`, `*-ConnectionPoolExhausted`, or `*-SlowQueries`
- Application logs: `query timeout after 10000ms`, `Connection is not available after 30000ms`
- Postgres logs: `FATAL: remaining connection slots are reserved for non-replication superuser connections`
- Grafana: connection pool utilization >90% or query P99 latency spike

**Desired outcome:** Query latency at baseline (<10ms P95 for reads), connection pool utilization below 70%, no timeout errors.

## Preconditions

- [ ] `psql` access to affected database (use superuser credentials for diagnostic queries)
- [ ] Grafana access to DB dashboards (connections, query latency, pool stats)
- [ ] Knowledge of which application is affected and which database it connects to
- [ ] DBA team contact information (for destructive operations like killing connections)

**Required tools:** psql, kubectl (for app-side logs/restart), Grafana, PgBouncer admin console (if applicable)

## Commands and Checks

### 1. Check active connection count vs. max

```bash
psql -U postgres -c "
  SELECT count(*) AS total,
    count(*) FILTER (WHERE state = 'active') AS active,
    count(*) FILTER (WHERE state = 'idle') AS idle,
    count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx
  FROM pg_stat_activity;"
# Compare total vs. max_connections:
psql -U postgres -c "SHOW max_connections;"
# IF total ≈ max_connections → pool exhausted
```

### 2. Identify long-running or blocked queries

```bash
psql -U postgres -c "
  SELECT pid, usename, state, wait_event_type, wait_event,
    now() - query_start AS duration, left(query, 80) AS query
  FROM pg_stat_activity
  WHERE state = 'active' AND now() - query_start > interval '5 seconds'
  ORDER BY duration DESC LIMIT 20;"
```

### 3. Check for lock contention

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

### 4. Check for connection leaks (long idle connections)

```bash
psql -U postgres -c "
  SELECT pid, usename, application_name, state,
    now() - state_change AS idle_duration
  FROM pg_stat_activity
  WHERE state = 'idle' AND now() - state_change > interval '30 minutes'
  ORDER BY idle_duration DESC LIMIT 20;"
# Large number of long-idle connections = likely connection leak
```

### 5. Check query performance (missing index?)

```bash
psql -U postgres -d <database> -c "
  EXPLAIN (ANALYZE, BUFFERS) <suspected-slow-query>;"
# IF Seq Scan on large table → missing index
# IF high buffer reads → table bloat or cold cache
```

### 6. Check replica lag (if reads go to replica)

```bash
psql -U postgres -c "
  SELECT client_addr,
    pg_size_pretty(sent_lsn - replay_lsn) AS replay_lag
  FROM pg_stat_replication;"
# On replica:
psql -U postgres -c "SELECT now() - pg_last_xact_replay_timestamp() AS lag;"
```

### 7. Check application-side connection pool

```bash
kubectl logs -l app=<service> -n <namespace> --tail=50 | grep -i "hikari\|connection\|pool"
# Look for: "Connection is not available", pool stats, active/idle counts
```

## Mitigation

### Scenario A: Connection pool exhausted by leaking connections

```bash
# Kill all idle connections older than 30 min from the offending application:
psql -U postgres -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE state = 'idle'
    AND application_name = '<service-name>'
    AND now() - state_change > interval '30 minutes';"
# Then restart the service to flush internal pool state:
kubectl rollout restart deployment/<service> -n <namespace>
```

### Scenario B: Lock contention (ALTER TABLE or long transaction blocking writes)

```bash
# Cancel the blocking query (non-destructive — query gets cancelled, not connection):
psql -U postgres -c "SELECT pg_cancel_backend(<blocking-pid>);"
# IF pg_cancel doesn't work (DDL in progress):
psql -U postgres -c "SELECT pg_terminate_backend(<blocking-pid>);"
```

### Scenario C: Missing index causing sequential scans and timeouts

```bash
# Create index concurrently (no table lock):
psql -U postgres -d <database> -c "
  CREATE INDEX CONCURRENTLY idx_<table>_<column>
  ON <table> (<column>);"
# Monitor build progress:
psql -U postgres -c "SELECT * FROM pg_stat_progress_create_index;"
```

### Scenario D: Replica lag causing stale reads

```bash
# Temporarily redirect reads to primary:
kubectl set env deployment/<service> -n <namespace> DB_READ_HOST=<primary-host>
kubectl rollout restart deployment/<service> -n <namespace>
# Kill backfill or bulk operation causing WAL pressure:
psql -U postgres -c "SELECT pg_cancel_backend(<backfill-pid>);"
```

### Scenario E: General timeout relief — increase statement timeout temporarily

```bash
# Application-side — if configurable via env var:
kubectl set env deployment/<service> -n <namespace> DB_STATEMENT_TIMEOUT_MS=30000
kubectl rollout restart deployment/<service> -n <namespace>
```

## Verification

- [ ] `pg_stat_activity` shows connection count well below `max_connections`
- [ ] No queries running longer than 5 seconds
- [ ] No lock waits visible
- [ ] Application error rate (timeouts) returned to 0%
- [ ] Connection pool metrics on Grafana stable below 70% utilization

```bash
psql -U postgres -c "
  SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '5s';"
# Expect: 0
kubectl logs -l app=<service> -n <namespace> --tail=20 | grep -c "timeout\|not available"
# Expect: 0
```

## Rollback

```bash
# If you terminated connections that shouldn't have been killed:
# — Service restart will recreate pool (no permanent damage)
kubectl rollout restart deployment/<service> -n <namespace>

# If you redirected reads to primary (Scenario D):
kubectl set env deployment/<service> -n <namespace> DB_READ_HOST=<replica-host>
kubectl rollout restart deployment/<service> -n <namespace>

# If you increased statement timeout:
kubectl set env deployment/<service> -n <namespace> DB_STATEMENT_TIMEOUT_MS=10000
kubectl rollout restart deployment/<service> -n <namespace>

# If index creation is causing issues, drop it:
psql -U postgres -d <database> -c "DROP INDEX CONCURRENTLY idx_<table>_<column>;"
```

## Escalation

| Condition | Escalate to | Channel |
|-----------|-------------|---------|
| Cannot identify slow query or lock holder in 15 min | DBA team | #data-eng |
| Connection count at max_connections and rising | DBA + platform team | PagerDuty P1 |
| Revenue service timeouts >20 min | Engineering Manager + IC | #incident-response |
| Data integrity concern (partial writes, stuck transactions) | DBA team immediately | #data-eng |
| Need to kill a production DDL migration | DBA approval required | #data-eng |

## Notes / Gotchas

- **Never kill connections blindly.** Always identify the application first. Killing connections from a critical service mid-transaction can cause data inconsistency.
- **`pg_cancel_backend` vs. `pg_terminate_backend`:** Cancel sends a polite "stop your query" signal. Terminate kills the connection entirely. Prefer cancel first.
- **Connection pool ≠ database connections.** If HikariCP is set to 20 but you see 200 DB connections, something is leaking. See [[INC-009-db-connection-pool-exhausted]].
- **ALTER TABLE during peak traffic** is the #1 cause of lock contention in this environment. See [[INC-018-db-lock-contention-payments]] — always use non-blocking DDL.
- **Missing indexes after migration** can cause latency to jump 1000×. See [[INC-008-db-timeout-auth-db]] — check `\d <table>` to verify expected indexes exist.
- **PgBouncer mode matters:** `session` mode holds connections per session; `transaction` mode releases after each transaction. For connection exhaustion, switching to `transaction` mode often fixes the problem.
