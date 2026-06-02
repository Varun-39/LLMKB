---
id: INC-006
title: Disk Full on Postgres Data Volume — Write Failures
severity: SEV-1
service: auth-service
environment: prod
category: outage
status: resolved
owner: Sara Ndiaye
assigned-to: Sara Ndiaye
date: 2026-05-10
duration: 41 minutes
created: 2026-05-10
updated: 2026-05-10
tags:
  - incident
  - disk
  - postgres
  - database
  - critical
  - prod
  - auth
related_runbooks:
  - "[[RB-002-disk-space-full]]"
  - "[[RB-004-db-timeouts]]"
related_incidents:
  - "[[INC-008-db-timeout-auth-db]]"
---

# INC-006 — Disk Full on Postgres Data Volume: Write Failures

## Summary

The Postgres primary for `auth-db` ran out of disk space on its data volume (`/dev/xvdf`) at 11:33 UTC on 2026-05-10. Postgres rejected all writes immediately, making new user registrations and session token writes fail. Read operations remained functional. The volume was expanded online and dead tuple bloat vacuumed, restoring full write capability after 41 minutes.

## Symptoms

- PagerDuty: `Postgres-DiskFull` at 11:35 UTC
- auth-service logs: `ERROR: could not extend file "base/16389/pg_wal": No space left on device`
- New user registration failing with HTTP 500 (`DB write error`)
- Session token refresh failing — users being logged out on token expiry
- Postgres `pg_stat_activity` showing transactions stuck in `idle in transaction`
- `df -h` on DB host: `/dev/xvdf 500G 500G 0 100%`

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | New registrations blocked; ~1,200 users logged out on token expiry |
| Services degraded | auth-service (write path down), api-gateway (auth-dependent writes failing) |
| Revenue impact | ~$8K in failed registrations during peak signup window |
| Duration | 11:33 → 12:14 UTC (41 min) |
| Data loss | None — writes rejected cleanly, no partial commits |

## Possible Causes

1. **Dead tuple bloat** — autovacuum not keeping up with high-churn `sessions` table, consuming excess disk
2. **WAL accumulation** — replication slot lag on the read replica causing WAL files to be retained
3. **Volume undersized** — data volume not resized after 3× user growth in last 60 days
4. **Unbounded audit log table** — growing without TTL or archival policy

## Troubleshooting Steps

1. Confirmed disk full on DB host
   ```bash
   ssh db-primary-01
   df -h /dev/xvdf
   # 500G / 500G used — 100%
   ```

2. Identified space consumers
   ```bash
   du -sh /var/lib/postgresql/14/main/* | sort -rh | head -5
   # 280G  base/
   # 198G  pg_wal/
   ```

3. Checked replication slot lag
   ```bash
   psql -U postgres -c "
     SELECT slot_name,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag
     FROM pg_replication_slots;"
   # replica-slot-01 | 191 GB
   ```

4. Identified bloated sessions table
   ```bash
   psql -U postgres -d auth_db -c "
     SELECT tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
     FROM pg_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 5;"
   # sessions: 212 GB (expected ~8 GB)
   ```

5. Confirmed dead tuple count
   ```bash
   psql -U postgres -d auth_db -c "
     SELECT n_dead_tup, n_live_tup FROM pg_stat_user_tables WHERE relname='sessions';"
   # n_dead_tup: 84,000,000  n_live_tup: 2,100,000
   ```

## Resolution

1. Dropped stale replication slot to immediately free WAL
   ```bash
   psql -U postgres -c "SELECT pg_drop_replication_slot('replica-slot-01');"
   # Disk: 500G → 262G used (52%)
   ```

2. Ran manual VACUUM on bloated sessions table
   ```bash
   psql -U postgres -d auth_db -c "VACUUM (VERBOSE, ANALYZE) sessions;"
   ```

3. Expanded EBS volume 500G → 1TB via AWS Console (online, no downtime)

4. Verified write path restored
   ```bash
   psql -U postgres -d auth_db -c "
     INSERT INTO sessions (id, user_id) VALUES (gen_random_uuid(), 1) RETURNING id;"
   # Returns row — writes working
   ```

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| DB writes failing >5 min | Page DBA + senior on-call | PagerDuty |
| Cannot free space within 15 min | Engage infra for emergency volume expansion | #platform-support |
| Read replica affected or data at risk | Page EM, consider failover | #incident-response |

## Post-Incident Notes

**Went well:**
- Dropping the replication slot freed enough space within minutes
- Online EBS volume expansion required no additional downtime

**Improve:**
- Replication slot lag had been growing for 8 days with no alert
- Autovacuum settings too conservative for high-churn sessions table
- No disk trend alert existed below 100% threshold

**Action items:**
- [x] Dropped lagging replication slot, vacuumed sessions table
- [x] Expanded volume to 1TB
- [ ] Add alert: replication slot lag >10 GB
- [ ] Add alert: disk >75% on all DB volumes
- [ ] Add TTL policy to sessions table (delete rows >30 days old)
- [ ] Tune autovacuum thresholds for high-churn tables

## Related Runbooks

- [[RB-002-disk-space-full]]
- [[RB-004-db-timeouts]]
