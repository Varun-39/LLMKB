---
id: INC-066
title: PostgreSQL WAL Archive Lag — pg_basebackup Blocked Slot Cleanup
severity: SEV-2
service: postgres-primary
environment: prod
category: capacity
date: 2026-06-10
duration: "45m"
tags:
  - incident
  - postgres
  - wal
  - archive
  - replication
  - disk
  - high
  - prod
---

## Summary

A `pg_basebackup` operation started 18 hours earlier for a new replica was still running (slow network transfer), holding the replication slot active. WAL segments accumulated to 120GB because the slot prevented cleanup. The database volume reached 92% capacity, triggering alerts. Without intervention, the database would have hit disk full within 2 hours.

## Symptoms

- PagerDuty: `Postgres-DiskSpaceHigh` at 14:00 UTC
- pg_wal directory: 120GB (normal: 2-5GB)
- Replication slot lag: 120GB behind current WAL position
- pg_basebackup: still transferring at 1.8MB/s (18 hours in)

## Diagnosis

1. Confirmed WAL accumulation
   ```bash
   du -sh /var/lib/postgresql/15/main/pg_wal/
   # 120G
   ```

2. Identified blocking replication slot
   ```bash
   psql -U postgres -c "SELECT slot_name, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag FROM pg_replication_slots;"
   # new_replica_slot | t | 120 GB
   ```

3. pg_basebackup process running for 18 hours (transferring over slow WAN link)

## Resolution

1. **Mitigate:** Cancelled the slow pg_basebackup and dropped the slot
   ```bash
   # Killed pg_basebackup process
   psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = 'pg_basebackup';"
   psql -U postgres -c "SELECT pg_drop_replication_slot('new_replica_slot');"
   ```

2. **Fix:** Checkpoint forced to trigger WAL cleanup
   ```bash
   psql -U postgres -c "CHECKPOINT;"
   # WAL dropped from 120GB to 2GB within minutes
   ```

3. **Verify:** Disk usage dropped to 65%

## Post-Incident Review

- pg_basebackup over slow links can hold WAL indefinitely
- Added alert: WAL directory >10GB
- Added replication slot lag alert: >5GB
- New replica provisioning now uses EBS snapshot + WAL replay (faster, no slot hold)

## Links

- Runbooks: [[RB-003-disk-space-full]]
- Related incidents: [[INC-006-disk-full-db-volume]], [[INC-017-db-read-replica-lag]]
