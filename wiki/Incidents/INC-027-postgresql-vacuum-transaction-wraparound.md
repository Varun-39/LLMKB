---
id: INC-027
title: PostgreSQL Vacuum Bloat Causing Transaction Wraparound Warning
severity: SEV-1
service: analytics-db
environment: prod
category: capacity
date: 2026-03-05
duration: "180m"
tags:
  - incident
  - postgresql
  - vacuum
  - transaction-wraparound
  - databases
---

## Summary

The analytics PostgreSQL database reached 85% of the transaction ID wraparound limit (2^31), triggering autovacuum to enter aggressive mode. This caused extreme I/O load, slowing all queries to a crawl. The database was 3 hours from entering safety shutdown mode which would have made it read-only.

## Symptoms

- PostgreSQL logs: `WARNING: database "analytics" must be vacuumed within 200000000 transactions`
- Query latency increased from 50ms to 12s across all analytics endpoints
- `pg_stat_activity` showing 40+ autovacuum workers running simultaneously
- Disk I/O at 100% utilization on database volume
- PagerDuty: `PostgreSQL-TransactionWraparound-Critical`
- Application timeouts on analytics dashboard

## Diagnosis

1. Checked wraparound status: `SELECT datname, age(datfrozenxid) FROM pg_database;` — analytics DB at 1.85 billion
2. Identified bloated tables: `SELECT relname, age(relfrozenxid) FROM pg_class ORDER BY age(relfrozenxid) DESC LIMIT 10;`
3. Found `events` table (2TB) had not been vacuumed in 6 months due to a long-running analytics query holding a transaction open
4. The idle-in-transaction session prevented vacuum from advancing the freeze horizon

## Resolution

1. Terminated the idle-in-transaction session: `SELECT pg_terminate_backend(<pid>);`
2. Manually ran vacuum on most critical tables: `VACUUM FREEZE VERBOSE events;`
3. Increased `maintenance_work_mem` to 2GB to accelerate vacuum
4. Set `idle_in_transaction_session_timeout = '10min'` to prevent recurrence
5. Monitored wraparound age decreasing over 3 hours until safe levels reached

## Post-Incident Review

Added transaction age monitoring with alerting at 500M and 1B thresholds. Implemented `idle_in_transaction_session_timeout` across all databases. Created weekly vacuum progress report. Partitioned the events table by month to reduce vacuum scope.

## Links
- Related: [[RB-030-postgresql-vacuum-wraparound-prevention]]
