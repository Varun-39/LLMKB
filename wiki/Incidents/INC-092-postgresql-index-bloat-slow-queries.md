---
id: INC-092
title: PostgreSQL Index Bloat Caused Slow Queries on Payments Table
severity: SEV-3
service: payment-service
environment: prod
category: degradation
date: 2026-04-25
duration: "2h 40m"
tags:
  - incident
  - postgres
  - index-bloat
  - slow-queries
  - payment-service
  - prod
  - database
error_family: unknown
resolution_runbook: RB-030
resolution_outcome: resolved
---

## Summary

The `payments` table index on `(status, created_at)` accumulated significant bloat (dead tuple ratio: 68%) after 6 months of high-churn payment status updates without a manual REINDEX. Query planner began preferring sequential scans over the bloated index, causing payment status queries to degrade from 8ms to 4,200ms, tripping the query latency SLA alert.

## Symptoms

- payment-service: `SELECT` queries on `payments` table timing out
- PagerDuty: `payment-query-latency P99 > 2000ms` alert fired
- `pg_stat_user_tables`: `payments` showing 4.2M dead tuples
- Grafana: payment-service P99 query latency: 4,200ms (SLA: 500ms)
- EXPLAIN on payment query: `Seq Scan` instead of `Index Scan`

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~900 users experiencing slow payment status checks |
| Services degraded | payment-service (status queries degraded) |
| Revenue impact | N/A — slow but not failing |
| Duration | 08:20 → 11:00 UTC (2h 40m) |
| Data loss | None |
| SLA breach | Yes — query latency SLA breached |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 08:20 | Query latency alert fired |
| 08:35 | On-call began investigation |
| 09:00 | Index bloat identified as root cause |
| 09:10 | REINDEX CONCURRENTLY started |
| 11:00 | REINDEX completed; query latency returned to normal |

## Diagnosis

1. Checked slow query log:
   ```bash
   psql -U postgres -d paymentdb -c "SELECT query, mean_exec_time, calls FROM pg_stat_statements WHERE query ILIKE '%payments%' ORDER BY mean_exec_time DESC LIMIT 5;"
   # SELECT * FROM payments WHERE status='pending' AND created_at > ... | mean_exec_time: 4231ms
   ```
2. Checked index bloat:
   ```bash
   psql -U postgres -d paymentdb -c "SELECT relname, n_dead_tup, n_live_tup, round(n_dead_tup::numeric/(n_live_tup+1)*100,1) AS dead_pct FROM pg_stat_user_tables WHERE relname='payments';"
   # payments | 4200000 | 1980000 | 68.0
   ```
3. Confirmed query planner avoiding index:
   ```bash
   psql -U postgres -d paymentdb -c "EXPLAIN SELECT * FROM payments WHERE status='pending' AND created_at > NOW()-INTERVAL '1 day';"
   # Seq Scan on payments (cost=0.00..98432.00 rows=...)
   ```

## Resolution

1. **Ran REINDEX CONCURRENTLY** (non-blocking):
   ```bash
   psql -U postgres -d paymentdb -c "REINDEX INDEX CONCURRENTLY idx_payments_status_created;"
   ```
2. **Ran VACUUM ANALYZE** on table:
   ```bash
   psql -U postgres -d paymentdb -c "VACUUM ANALYZE payments;"
   ```
3. **Verified index now used:**
   ```bash
   psql -U postgres -d paymentdb -c "EXPLAIN SELECT * FROM payments WHERE status='pending' AND created_at > NOW()-INTERVAL '1 day';"
   # Index Scan using idx_payments_status_created
   ```
4. Query latency returned to 8ms

## Post-Incident Review

**What went well:**
- REINDEX CONCURRENTLY completed without any application downtime

**What needs improvement:**
- No routine index health monitoring
- High-churn tables not identified for proactive VACUUM scheduling

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add weekly REINDEX job for high-churn tables (payments, events) | DBA | 2026-05-02 | Open |
| Add alert: table dead tuple ratio > 40% | Observability | 2026-05-02 | Open |

## Links

- Runbooks: [[RB-030-postgresql-vacuum-wraparound-prevention]], [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-027-postgresql-vacuum-transaction-wraparound]], [[INC-078-postgresql-vacuum-wraparound]]
