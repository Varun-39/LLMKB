---
id: INC-006
title: Disk Full on Postgres Data Volume — Write Failures
severity: SEV-1
service: auth-service
environment: prod
category: outage
date: 2026-05-10
duration: "41m"
detection_gap: "2m"
tags:
  - incident
  - disk
  - postgres
  - critical
  - prod
  - auth
---

## Summary

The Postgres primary for `auth-db` ran out of disk space on its data volume (`/dev/xvdf`) at 11:33 UTC on 2026-05-10. Postgres rejected all writes, making new user registrations and session token writes fail. The volume was expanded online and dead tuple bloat vacuumed, restoring full write capability after 41 minutes.

## Symptoms

- PagerDuty: `Postgres-DiskFull` fired at 11:35 UTC
- auth-service logs: `ERROR: could not extend file "base/16389/pg_wal": No space left on device`
- New user registration failing with HTTP 500 (`DB write error`)
- Session token refresh failing — users being logged out on token expiry
- `pg_stat_activity`: transactions stuck in `idle in transaction`
- `df -h`: `/dev/xvdf 500G 500G 0 100%`

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | New registrations blocked; ~1,200 users logged out on token expiry |
| Services degraded | auth-service (write path down), api-gateway (auth-dependent writes failing) |
| Revenue impact | ~$8K in failed registrations during peak signup window |
| Duration | 11:33 → 12:14 UTC (41 min) |
| Data loss | None — writes rejected cleanly, no partial commits |
| SLA breach | Yes — enterprise SLA (99.9% uptime) breached |
| Customer comms | Status page updated at 11:40 UTC |

## Timeline

| Time (UTC) | Event                                                            |
| ---------- | ---------------------------------------------------------------- |
| 11:33      | Disk reached 100%, Postgres write failures began                 |
| 11:35      | Alert fired                                                      |
| 11:36      | On-call acknowledged (Sara Ndiaye)                               |
| 11:42      | Root cause isolated — replication slot lag + session table bloat |
| 11:50      | Stale replication slot dropped, 48% disk freed                   |
| 12:02      | VACUUM completed on sessions table                               |
| 12:10      | EBS volume expanded 500G → 1TB                                   |
| 12:14      | Write path fully restored, incident closed                       |

## Diagnosis

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

3. Checked replication slot lag — found massive WAL retention
   ```bash
   psql -U postgres -c "
     SELECT slot_name,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag
     FROM pg_replication_slots;"
   # replica-slot-01 | 191 GB
   ```

4. Identified bloated sessions table — 84M dead tuples
   ```bash
   psql -U postgres -d auth_db -c "
     SELECT n_dead_tup, n_live_tup FROM pg_stat_user_tables WHERE relname='sessions';"
   # n_dead_tup: 84,000,000  n_live_tup: 2,100,000
   ```

## Resolution

1. **Mitigate:** Dropped stale replication slot to immediately free WAL space
   ```bash
   psql -U postgres -c "SELECT pg_drop_replication_slot('replica-slot-01');"
   # Disk: 500G → 262G used (52%)
   ```

2. **Fix:** Ran manual VACUUM and expanded volume to prevent recurrence
   ```bash
   psql -U postgres -d auth_db -c "VACUUM (VERBOSE, ANALYZE) sessions;"
   # AWS Console: EBS volume expanded 500G → 1TB (online, no downtime)
   ```

3. **Verify:** Confirmed write path restored
   ```bash
   psql -U postgres -d auth_db -c "
     INSERT INTO sessions (id, user_id) VALUES (gen_random_uuid(), 1) RETURNING id;"
   # Returns row — writes working
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| DB writes failing >5 min | Page DBA + senior on-call | PagerDuty |
| Cannot free space within 15 min | Engage infra for emergency volume expansion | #platform-support |
| Read replica affected or data at risk | Page EM, consider failover | #incident-response |

## Post-Incident Review

**What went well:**
- Dropping the replication slot freed enough space within minutes
- Online EBS volume expansion required no additional downtime

**What needs improvement:**
- Replication slot lag had been growing for 8 days with no alert
- Autovacuum settings too conservative for high-churn sessions table
- No disk trend alert existed below 100% threshold

**Contributing factors (beyond root cause):**
- 3× user growth in last 60 days without volume resize review
- No TTL or archival policy on sessions table
- Read replica was offline for maintenance, slot accumulated unchecked

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add alert: replication slot lag >10 GB | SRE team | 2026-05-24 | Open |
| Add alert: disk >75% on all DB volumes | SRE team | 2026-05-24 | Open |
| Add TTL policy to sessions table (delete rows >30 days old) | Sara Ndiaye | 2026-05-31 | Open |
| Tune autovacuum thresholds for high-churn tables | DBA team | 2026-05-31 | Open |

## Links

- Runbooks: [[RB-003-disk-space-full]], [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-008-db-timeout-auth-db]]
- PR/commit: N/A
- Post-mortem doc: N/A
