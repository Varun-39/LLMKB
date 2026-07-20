---
id: SYS-002
name: payment-service
environment: prod
criticality: critical
primary team: Payments Team
support team: Platform / SRE
vendor: Internal Application
status: active
customer facing: yes
last updated: 2026-06-16
tags:
  - system
  - payments
  - kubernetes
  - postgres
  - critical
  - prod
---

## System Overview

The payment-service handles payment initiation and transaction processing for the platform. It writes payment records to the `payments_db` Postgres database and is a critical dependency for the checkout flow.

- **What it does:** Initiates and records payment transactions, manages payment state
- **Why it exists:** Provides the core transaction write path for all customer payments
- **Business process:** Payment processing and order checkout
- **Customer facing:** Yes — all payment initiation flows depend on this service

---

## Business Function

Payment processing.

The payment-service enables:

- Payment initiation (`POST /payments/initiate`)
- Recording payment transactions to `payment_transactions`
- Payment state management and processor fee tracking
- Supporting the downstream checkout-service flow

---

## Ownership & Support

### Primary Team

Payments Team — owns development, on-call, and incident response (service owner: Priya Sharma per incident records).

### Support Team

Platform / SRE and DBA team — engaged for infrastructure, Kubernetes, and database escalations.

### Vendor

Internal Application — developed and maintained in-house.

---

## Architecture Summary

- **Application type:** Microservice (REST API)
- **Deployment model:** Kubernetes Deployment
- **Hosting platform:** Kubernetes (prod cluster)
- **Runtime technology:** JVM-based (uses HikariCP connection pool)
- **Namespace:** `payments`
- **Container image:** `registry.internal/payment-service`

---

## Key Dependencies

### Internal Dependencies

- **[[SYS-005-postgres-primary]]** (payments_db) — stores payment transactions
- **[[SYS-004-api-gateway]]** — routes inbound payment requests
- **checkout-service** — downstream consumer; blocked when payment writes fail

### External Dependencies

- PostgreSQL Database (payments_db — `payment_transactions` table)
- PagerDuty (alerting)
- Grafana / Datadog (metrics)

---

## Interfaces

| Interface | Type | Direction | Description |
|-----------|------|-----------|-------------|
| `/payments/initiate` | REST API | Inbound | Payment initiation endpoint |
| payments_db | PostgreSQL | Outbound | Transaction persistence (via HikariCP) |
| api-gateway | HTTP | Inbound | Request routing |
| checkout-service | HTTP | Inbound | Downstream checkout dependency |

---

## Environment Details

| Attribute | Value |
|-----------|-------|
| Kubernetes namespace | `payments` |
| Cluster | prod cluster |
| Database | payments_db (`payment_transactions` table) |
| Connection pool | HikariCP |
| Container image | `registry.internal/payment-service` |
| SLA | 99.95% uptime (payments SLA) |

---

## Monitoring & Alerting

| Monitor | Tool | Description |
|---------|------|-------------|
| `PaymentService-HighErrorRate` | PagerDuty | Fires on elevated payment write error rate |
| `PaymentService-WriteLatencyHigh` | PagerDuty | Fires when write P99 latency spikes |
| Payment success rate | Grafana | Tracks percentage of successful payments |
| Write P99 latency | Grafana | Tracks payment write latency |
| Connection pool utilization | Grafana | HikariCP pool stats |

---

## Common Failure Scenarios

| Failure Scenario | Related Incidents | Related Runbooks |
|------------------|-------------------|------------------|
| Rollback without reverting DB migration | [[INC-011-rollback-failed-frontend]] | [[RB-006-failed-deployment-rollback]] |
| DB lock contention from blocking DDL | [[INC-018-db-lock-contention-payments]] | [[RB-005-database-timeout-connection-exhaustion]] |
| Connection pool exhaustion | [[INC-018-db-lock-contention-payments]] | [[RB-005-database-timeout-connection-exhaustion]] |
| Pod crash / CrashLoopBackOff | — | [[RB-007-pod-crash-investigation]] |
| High CPU saturation | — | [[RB-004-high-cpu-usage]] |

---

## Related Incidents

- [[INC-011-rollback-failed-frontend]] — failed rollback, DB migration not reverted
- [[INC-018-db-lock-contention-payments]] — DB lock contention stalled writes

---

## Related Runbooks

- [[RB-006-failed-deployment-rollback]]
- [[RB-005-database-timeout-connection-exhaustion]]
- [[RB-007-pod-crash-investigation]]
- [[RB-004-high-cpu-usage]]

---

## Escalation Information

| Trigger | Action | Channel |
|---------|--------|---------|
| Payments failing > 2% for > 5 min | Page on-call SRE + DBA | PagerDuty |
| Revenue impact > $10K estimated | Page EM + IC | #incident-response |
| DB schema conflict suspected | Engage DBA team | #data-eng |
| Rollback causes new failure within 5 min | Page EM + IC immediately | #incident-response |
| Need to kill a production DDL migration | DBA approval required | #data-eng |

Governance references: [[Escalation Rules]], [[Guardrails]]

---

## Additional Notes

- Migrations must follow the expand-then-contract pattern (backward-compatible). A non-nullable column added in v6.0.0 broke the rolled-back v5.9.3 code — see INC-011.
- Every up migration must ship with a down migration.
- Avoid blocking DDL (`ALTER TABLE`) during peak hours (17:00–23:00 UTC). Use non-blocking patterns and set `lock_timeout` on migration sessions — see INC-018.
- Direct prod DB access for non-DBA engineers is restricted following INC-018.

---
