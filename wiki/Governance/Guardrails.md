---
id: GR-001
title: Database Migration Safety Guardrails
type: guardrail
version: 2.1.0
scope: database
enforcement: mandatory
status: active
owner: DBA Team
approved_by: VP Engineering
effective_date: 2026-03-15
review_date: 2026-06-15
next_review_date: 2026-09-15
created: 2026-03-15
updated: 2026-05-10
tags:
  - guardrail
  - database
  - postgres
  - migrations
  - prod
triggering_incident:
  - "[[INC-018-db-lock-contention-payments]]"
related_incidents:
  - "[[INC-008-db-timeout-auth-db]]"
  - "[[INC-011-rollback-failed-frontend]]"
  - "[[INC-006-disk-full-db-volume]]"
---

## Rule Statement

All database schema migrations targeting production environments MUST use non-blocking DDL patterns, MUST NOT execute during peak traffic hours (08:00–22:00 UTC), MUST include a verified rollback path, and MUST pass automated pre-flight validation before execution.

## Rationale

Database migrations have been the root cause or primary contributing factor in four of our five most severe production incidents within the past 90 days:

- **INC-018:** An ALTER TABLE with AccessExclusiveLock blocked all payment writes for 23 minutes during peak hours, costing ~$61K in blocked transactions.
- **INC-011:** A forward-only migration without a down path caused 73 minutes of payment outage (~$67K impact) when the application was rolled back but the schema was not.
- **INC-008:** A CASCADE drop silently removed a critical index, degrading auth-service for 55 minutes.
- **INC-006:** Unchecked dead tuple bloat and replication slot lag filled a production volume.

- **Business justification:** Combined revenue impact from migration-related incidents exceeds $140K. Enterprise SLA breaches from these events have triggered contractual penalty discussions. Each incident also carried reputational cost to customer trust.
- **Frequency of past violations:** 4 incidents in 90 days (March–May 2026), averaging one migration-caused outage every 3 weeks.

## Scope

| Attribute | Value |
|-----------|-------|
| Applies to | All engineering teams executing schema changes against production databases |
| Enforcement level | Mandatory — violations block deployment |
| Environments | Production (mandatory), Staging (advisory) |
| Exceptions | VP Engineering approval required; documented in #change-management with expiry date |

## Rule Details

### What is Prohibited / Required

| Allowed | Prohibited |
|---------|------------|
| `ALTER TABLE ... ADD COLUMN col_name type` (nullable, no default lock) | `ALTER TABLE ... ADD COLUMN col_name type NOT NULL` without default (requires table rewrite) |
| `CREATE INDEX CONCURRENTLY` | `CREATE INDEX` (non-concurrent — holds lock) |
| Expand-then-contract pattern (add nullable → backfill → add constraint) | Single-step non-nullable column additions on existing tables |
| Migrations with tested down/rollback migration | Forward-only migrations with no rollback path |
| DDL execution during maintenance window (02:00–06:00 UTC) | DDL execution during peak hours (08:00–22:00 UTC) |
| `lock_timeout = 3s` set on migration session | Migration sessions with default `lock_timeout = 0` (infinite) |
| Schema changes via CI/CD pipeline with pre-flight checks | Direct production database access for schema changes |
| `DROP COLUMN` with explicit index preservation verification | `DROP COLUMN ... CASCADE` without reviewing dependent objects |

### Conditions / Thresholds

| Condition | Threshold |
|-----------|-----------|
| Peak traffic hours (DDL prohibited) | 08:00–22:00 UTC, Monday–Sunday |
| Maintenance window (DDL permitted) | 02:00–06:00 UTC, with 24h advance notice in #change-management |
| Maximum lock wait time for migration sessions | 3 seconds (`lock_timeout = '3s'`) |
| Index creation on tables > 1M rows | Must use `CONCURRENTLY` |
| Migration must pass staging with prod-scale data | Required for tables > 10M rows |
| Rollback migration tested | Required for all migrations — verified in staging before prod execution |

### Exception Process

1. **Request:** Engineer submits exception request in #change-management with: migration SQL, justification, risk assessment, rollback plan, and proposed execution window.
2. **Review:** DBA team reviews within 4 business hours and provides technical assessment.
3. **Approval:** VP Engineering grants written approval in the thread. Verbal approvals are not valid.
4. **Documentation:** Exception is logged in the Governance audit log with an expiry date (maximum 7 days).
5. **Execution:** Migration runs under DBA supervision with real-time monitoring.

## Detection / Enforcement

### How Violations Are Detected

- **CI/CD pipeline:** `pg-migration-lint` runs against all migration files at PR time; blocks merge on violation
- **Database audit logging:** All DDL statements logged with session user, timestamp, and `lock_timeout` value
- **PagerDuty alert:** `DDL-PeakHours-Violation` fires if any DDL is detected on production during 08:00–22:00 UTC
- **Quarterly audit:** DBA team reviews all migrations executed in the quarter against this policy

### Automated Enforcement

```yaml
# CI pipeline check (.github/workflows/migration-lint.yml)
migration-safety-check:
  runs-on: ubuntu-latest
  steps:
    - name: Lint migration files
      run: |
        pg-migration-lint \
          --require-concurrent-index \
          --require-lock-timeout \
          --require-down-migration \
          --forbid-cascade-without-verification \
          --forbid-not-null-without-default \
          db/migrations/*.sql

# Postgres session defaults for migration user (applied via connection pooler)
# SET lock_timeout = '3s';
# SET statement_timeout = '300s';
```

### Manual Enforcement

- **Code review:** PR checklist includes "Migration follows expand-then-contract pattern" and "Down migration provided and tested"
- **Deployment checklist:** Deployer confirms migration window, verifies `lock_timeout` is set, confirms rollback path exists
- **Weekly DBA review:** All migrations merged in the past week are reviewed for compliance

## Response to Violations

| Severity of Violation | Response |
|-----------------------|----------|
| Violation detected during active incident | Revert immediately (`pg_cancel_backend` or rollback migration); document in post-mortem |
| Caught in CI/CD (pre-merge) | Block merge; engineer must fix before re-submitting |
| Caught in staging (pre-prod) | Block promotion to production; DBA team advises on correction |
| Caught post-production (no impact observed) | Create P2 follow-up ticket; DBA reviews within 48 hours |
| Repeated violations by same team (3+ in 30 days) | Escalate to Engineering Manager; team must complete migration safety training |

## Related Guardrails

- GR-002 — Production Database Access Control (direct prod DB access restricted to DBA team)
- GR-003 — Deployment Rollback Requirements (all deployments must have verified rollback path)
- GR-004 — Disk and Volume Capacity Management (alert thresholds and expansion policies)

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-03-15 | DBA Team | Initial publication following INC-018 lock contention incident |
| 2026-04-14 | Priya Sharma | Added rollback requirement after INC-011 migration/rollback mismatch |
| 2026-05-01 | Sara Ndiaye | Added CASCADE verification rule after INC-008 index loss |
| 2026-05-10 | DBA Team | Added disk/bloat monitoring cross-reference after INC-006; bumped to v2.1.0 |
