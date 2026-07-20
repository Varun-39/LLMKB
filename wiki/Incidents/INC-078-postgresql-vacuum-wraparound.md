---
id: INC-078
title: PostgreSQL Transaction ID Wraparound Due to Vacuum Bloat
severity: SEV-1
service: order-database
environment: prod
category: outage
date: 2026-02-25
duration: "3h20m"
tags:
  - incident
  - postgresql
  - vacuum
  - database
  - transaction-wraparound
  - critical
---

## Summary

The `order-database` PostgreSQL instance entered safety shutdown mode when transaction ID usage reached the wraparound protection threshold (2 billion XIDs). The database became read-only, blocking all write operations for 3 hours while emergency vacuum ran. Root cause: autovacuum was disabled on 3 large tables during a migration 6 months ago and never re-enabled.

## Symptoms

- Application errors: `ERROR: database is not accepting commands to avoid wraparound data loss`
- PagerDuty: `PostgreSQL-ReadOnly-Emergency` at 09:14 UTC
- All writes to order tables failing with error code 25P03
- `pg_stat_activity` showed autovacuum running aggressively (emergency anti-wraparound)
- Remaining XIDs approaching zero in `pg_database.datfrozenxid`

## Diagnosis

1. Checked transaction age:
   ```sql
   SELECT datname, age(datfrozenxid) FROM pg_database ORDER BY 2 DESC;
   -- orders_db: 1,999,847,322 (dangerously close to 2B limit)
   ```
2. Found 3 tables with autovacuum disabled:
   ```sql
   SELECT relname, reloptions FROM pg_class WHERE reloptions::text LIKE '%autovacuum_enabled=false%';
   -- orders, order_items, order_history
   ```
3. These tables were set `autovacuum_enabled=false` during a bulk data migration on 2025-08-12 and never reverted

## Resolution

1. Increased `autovacuum_work_mem` temporarily:
   ```sql
   ALTER SYSTEM SET autovacuum_work_mem = '2GB';
   SELECT pg_reload_conf();
   ```
2. Manually triggered aggressive vacuum:
   ```sql
   VACUUM (FREEZE, VERBOSE) orders;
   VACUUM (FREEZE, VERBOSE) order_items;
   VACUUM (FREEZE, VERBOSE) order_history;
   ```
3. Re-enabled autovacuum on all tables:
   ```sql
   ALTER TABLE orders RESET (autovacuum_enabled);
   ALTER TABLE order_items RESET (autovacuum_enabled);
   ALTER TABLE order_history RESET (autovacuum_enabled);
   ```
4. Monitored until XID age dropped below 500 million

## Post-Incident Review

- Never disable autovacuum without a follow-up task to re-enable
- Added alert: `pg_database_age > 1.5 billion` → SEV-2 page
- Added weekly check script for tables with autovacuum disabled
- Migration runbooks now include "re-enable autovacuum" as a mandatory post-migration step

## Links

- Related: [[RB-030-postgresql-vacuum-wraparound-prevention]]
