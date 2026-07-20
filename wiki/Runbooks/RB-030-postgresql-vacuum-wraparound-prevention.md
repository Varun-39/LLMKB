---
id: RB-030
title: PostgreSQL Vacuum and Transaction ID Wraparound Prevention
service: postgres-primary
related_services:
  - payment-service
  - auth-service
  - reporting-service
severity: SEV-1
environment: prod
category: resource-exhaustion
risk_level: high
estimated_duration: "30m"
approval_required: yes
approver_role: DBA Lead
tags:
  - runbook
  - postgres
  - vacuum
  - wraparound
  - database
  - prod
related_incidents:
  - "[[INC-027-postgresql-vacuum-transaction-wraparound]]"
  - "[[INC-027-postgresql-vacuum-wraparound]]"
related_runbooks:
  - "[[RB-005-database-timeout-connection-exhaustion]]"
  - "[[RB-003-disk-space-full]]"
related_guardrails: []
---

## Purpose

Prevent and recover from PostgreSQL transaction ID wraparound by monitoring autovacuum health, resolving blocked vacuums, and executing emergency VACUUM FREEZE when needed.

**Desired outcome:** All tables vacuumed below wraparound danger threshold, autovacuum running efficiently, no wraparound risk.

## Success Criteria

- No tables with `age(datfrozenxid)` > 150 million (warning) or > 1 billion (danger)
- Autovacuum running without being blocked by long transactions
- No `WARNING: database must be vacuumed within X transactions` in logs
- VACUUM operations completing in reasonable time

## Scope

| Attribute | Value |
|-----------|-------|
| Service | postgres-primary |
| Related services | payment-service, auth-service, reporting-service |
| Environments | prod |
| Use when | `*-XIDWraparoundRisk`, autovacuum blocked, or approaching wraparound threshold |
| Do NOT use when | Normal routine maintenance (let autovacuum handle it) |
| Risk level | High (if wraparound reached, DB goes read-only) |
| Estimated duration | 25–30 minutes |
| Approval required | Yes — DBA Lead |

## Prerequisites

- [ ] `psql` superuser access to affected database
- [ ] DBA Lead approval (for manual VACUUM operations)
- [ ] Understanding of table sizes and activity patterns
- [ ] Maintenance window if VACUUM FREEZE needed on large tables

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `psql` | Database queries and VACUUM operations | Superuser |
| Grafana | Transaction age metrics | Read access |
| `pg_stat_activity` | Autovacuum monitoring | Superuser |

## Trigger

- Alert: `*-XIDWraparoundRisk` (age approaching 200M transactions)
- Log: `WARNING: database "prod" must be vacuumed within 100000000 transactions`
- Symptom: Autovacuum workers running but never completing
- Metric: `age(datfrozenxid)` trending upward without plateauing

## Triage

1. Check current transaction age
   ```bash
   psql -U postgres -c "SELECT datname, age(datfrozenxid) AS xid_age, 
     round(age(datfrozenxid)::numeric / 2000000000 * 100, 2) AS pct_to_wraparound 
     FROM pg_database ORDER BY xid_age DESC;"
   # What to look for: >150M = warning, >500M = urgent, >1B = emergency
   ```

2. Check which tables need vacuum most
   ```bash
   psql -U postgres -d <db> -c "SELECT schemaname, relname, 
     n_dead_tup, last_vacuum, last_autovacuum,
     age(relfrozenxid) AS xid_age
     FROM pg_stat_user_tables ORDER BY xid_age DESC LIMIT 10;"
   ```

3. Check if autovacuum is running
   ```bash
   psql -U postgres -c "SELECT pid, datname, relid::regclass, phase, 
     heap_blks_scanned, heap_blks_total
     FROM pg_stat_progress_vacuum;"
   ```

## Investigation

1. **Check if autovacuum is blocked by long transactions**
   ```bash
   psql -U postgres -c "SELECT pid, usename, state, 
     now()-xact_start AS xact_duration, left(query,60)
     FROM pg_stat_activity 
     WHERE xact_start < now() - interval '1 hour'
     ORDER BY xact_start;"
   # What to look for: long-running transactions preventing tuple freezing
   ```

2. **Check autovacuum settings**
   ```bash
   psql -U postgres -c "SHOW autovacuum_freeze_max_age; SHOW vacuum_freeze_min_age;"
   ```

3. **Check table bloat**
   ```bash
   psql -U postgres -d <db> -c "SELECT relname, 
     pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
     n_dead_tup
     FROM pg_stat_user_tables WHERE n_dead_tup > 100000 ORDER BY n_dead_tup DESC LIMIT 10;"
   ```

4. **Decision point:**
   - IF long transaction blocking vacuum → proceed to Mitigation Option A
   - IF autovacuum too slow (large table) → proceed to Mitigation Option B
   - IF approaching wraparound danger (>500M) → proceed to Mitigation Option C

## Mitigation

### Option A: Kill blocking long transaction

```bash
psql -U postgres -c "SELECT pg_terminate_backend(<blocking-pid>);"
# Autovacuum should resume automatically
```

### Option B: Speed up autovacuum for specific table

```bash
psql -U postgres -d <db> -c "ALTER TABLE <table> SET (autovacuum_vacuum_cost_delay = 0);"
# This makes vacuum run at full speed on this table
# Reset after vacuum completes:
# ALTER TABLE <table> RESET (autovacuum_vacuum_cost_delay);
```

### Option C: Emergency VACUUM FREEZE

```bash
# ⚠️ This can take hours on large tables and causes I/O load
psql -U postgres -d <db> -c "VACUUM (FREEZE, VERBOSE) <table>;"
# Monitor progress:
psql -U postgres -c "SELECT phase, heap_blks_scanned, heap_blks_total,
  round(heap_blks_scanned::numeric / heap_blks_total * 100, 1) AS pct_done
  FROM pg_stat_progress_vacuum;"
```

**After mitigation:** Monitor transaction age — should stop growing or decrease.

## Verification

- [ ] `age(datfrozenxid)` decreasing or stable below threshold
- [ ] Autovacuum workers active and completing
- [ ] No wraparound warnings in logs
- [ ] No long-running transactions blocking vacuum

```bash
psql -U postgres -c "SELECT datname, age(datfrozenxid) FROM pg_database ORDER BY 2 DESC;"
# Expected: all below 150M and stable/decreasing
```

## Failure Signals

- Vacuum cannot run (locked out by concurrent DDL)
- Vacuum running but age not decreasing (wrong table targeted)
- Disk space insufficient for vacuum operation (VACUUM generates WAL)
- I/O load from vacuum causing application timeouts

## Rollback

1. **If vacuum causing performance issues:** Cancel it
   ```bash
   psql -U postgres -c "SELECT pg_cancel_backend(<vacuum-pid>);"
   ```
2. **Reset table-level vacuum settings:** `ALTER TABLE <table> RESET (autovacuum_vacuum_cost_delay);`

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| age > 1 billion (imminent read-only) | DBA Lead + EM + CTO | PagerDuty P1 | Immediate |
| VACUUM cannot complete (hours of attempts) | DBA team | #data-eng | 10 min |
| Vacuum causing application impact | DBA + SRE | #incident-response | 10 min |

## Notes

- **At 2 billion transactions, PostgreSQL goes read-only to prevent wraparound.** This is catastrophic and non-recoverable without VACUUM.
- **Long-running transactions are the #1 blocker of autovacuum.** Monitor and kill transactions >1 hour.
- **VACUUM FREEZE on a 500GB table** can take 4-8 hours and generate significant WAL.
- **Never disable autovacuum** on production tables — it's there for a reason.
- See [[INC-027-postgresql-vacuum-transaction-wraparound]] for a real close call.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Monthly
- **Next review:** 2026-07-15
- **Test method:** Check transaction ages monthly, run manual VACUUM FREEZE on staging large table.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | DBA Team | Initial publication |
