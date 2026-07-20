---
id: SYS-005
name: postgres-primary
environment: prod
criticality: critical
primary team: DBA Team
support team: Platform / SRE
vendor: PostgreSQL (self-managed on AWS)
status: active
customer facing: no
last updated: 2026-06-16
tags:
  - system
  - database
  - postgres
  - infrastructure
  - critical
  - prod
---

## System Overview

postgres-primary is the primary PostgreSQL database server backing multiple core services, including auth-service (`auth_db`) and payment-service (`payments_db`). It is the shared system of record for sessions, credentials, and payment transactions, and is a frequent source of incidents (disk exhaustion, lock contention, missing indexes, connection exhaustion).

- **What it does:** Stores and serves relational data for core platform services
- **Why it exists:** Provides durable, transactional persistence for auth and payment data
- **Business process:** Data persistence underpinning authentication and payments
- **Customer facing:** No — internal data tier, but failures cascade to customer-facing services

---

## Business Function

Relational data persistence (system of record).

postgres-primary provides:

- Session and credential storage for auth-service (`auth_db`)
- Payment transaction storage for payment-service (`payments_db`)
- Transactional guarantees for write-critical paths
- Read replication for read-heavy workloads

---

## Ownership & Support

### Primary Team

DBA Team — owns database administration, schema/migration review, and tuning.

### Support Team

Platform / SRE — engaged for volume expansion, node, and infrastructure operations.

### Vendor

PostgreSQL — self-managed on AWS (EBS-backed volumes). Not a managed RDS instance per incident records (manual volume expansion, replication slot management).

---

## Architecture Summary

- **Application type:** Relational database (PostgreSQL 14)
- **Deployment model:** Primary with read replica(s); physical replication slots
- **Hosting platform:** AWS EC2 with EBS-backed data volumes (e.g., `/dev/xvdf`)
- **Host (primary):** `db-primary-01`
- **Connection pooling:** PgBouncer in front of the database

---

## Key Dependencies

### Internal Dependencies

- **[[SYS-001-auth-service]]** — consumer (`auth_db`)
- **[[SYS-002-payment-service]]** — consumer (`payments_db`)
- **reporting-service** — read consumer
- **pgbouncer** — connection pooler

### External Dependencies

- AWS EBS (data volumes — online expansion supported)
- AWS EC2 (database hosts)
- PagerDuty (alerting)

---

## Interfaces

| Interface | Type | Direction | Description |
|-----------|------|-----------|-------------|
| PostgreSQL wire protocol (5432) | TCP | Inbound | Client connections from services |
| PgBouncer | Connection pool | Inbound | Pooled connections from applications |
| Physical replication | Streaming | Outbound | WAL streaming to read replica(s) |

---

## Environment Details

| Attribute | Value |
|-----------|-------|
| Engine | PostgreSQL 14 |
| Primary host | `db-primary-01` |
| Data volume | EBS (`/dev/xvdf`), expanded 500G → 1TB (INC-006) |
| Databases | `auth_db`, `payments_db` |
| Key tables | `sessions` (~80M rows), `payment_transactions` |
| Connection pooler | PgBouncer |
| Statement timeout | 10s default (raised to 30s during incidents) |

---

## Monitoring & Alerting

| Monitor | Tool | Description |
|---------|------|-------------|
| `Postgres-DiskFull` | PagerDuty | Fires when data volume reaches capacity |
| `*-DBTimeout` | PagerDuty | Query timeout alerts |
| `*-ConnectionPoolExhausted` | PagerDuty | Connection pool exhaustion |
| `*-SlowQueries` | PagerDuty | Slow query alerts |
| Connection count vs. max_connections | Grafana | Connection utilization |
| Replication slot lag | Grafana | WAL retention / replica lag |
| Disk utilization | Grafana | Volume usage trend |

---

## Common Failure Scenarios

| Failure Scenario | Related Incidents | Related Runbooks |
|------------------|-------------------|------------------|
| Disk full on data volume (WAL + bloat) | [[INC-006-disk-full-db-volume]] | [[RB-003-disk-space-full]] |
| Query timeout from missing index | [[INC-008-db-timeout-auth-db]] | [[RB-005-database-timeout-connection-exhaustion]] |
| Lock contention from blocking DDL | [[INC-018-db-lock-contention-payments]] | [[RB-005-database-timeout-connection-exhaustion]] |
| Connection pool exhaustion | [[INC-009-db-connection-pool-exhausted]] | [[RB-005-database-timeout-connection-exhaustion]] |
| Read replica lag | [[INC-017-db-read-replica-lag]] | [[RB-005-database-timeout-connection-exhaustion]] |

---

## Related Incidents

- [[INC-006-disk-full-db-volume]] — disk full from replication slot lag + table bloat
- [[INC-008-db-timeout-auth-db]] — missing index after migration caused seq scans
- [[INC-018-db-lock-contention-payments]] — blocking ALTER TABLE stalled writes

---

## Related Runbooks

- [[RB-005-database-timeout-connection-exhaustion]]
- [[RB-003-disk-space-full]]

---

## Escalation Information

| Trigger | Action | Channel |
|---------|--------|---------|
| DB writes failing > 5 min | Page DBA + senior on-call | PagerDuty |
| Connection count at max_connections and rising | DBA + platform team | PagerDuty P1 |
| Cannot free disk space within 15 min | Engage infra for emergency volume expansion | #platform-support |
| Need to kill a production DDL migration | DBA approval required | #data-eng |
| Data integrity concern (partial writes, stuck tx) | DBA team | #data-eng |

Governance references: [[Escalation Rules]], [[Guardrails]]

---

## Additional Notes

- Replication slot lag is the #1 cause of WAL accumulation and disk-full incidents — a single lagging slot retained 191 GB of WAL in INC-006. Monitor slot lag and drop stale slots from decommissioned replicas.
- `CASCADE` in migrations can silently drop dependent indexes — always validate expected indexes post-migration (see INC-008).
- Avoid blocking DDL during peak hours (17:00–23:00 UTC); set `lock_timeout` on migration sessions (see INC-018).
- Use `CREATE INDEX CONCURRENTLY` and the expand-then-contract pattern for zero-downtime schema changes.
- High-churn tables like `sessions` need tuned autovacuum and a TTL/archival policy.

---
