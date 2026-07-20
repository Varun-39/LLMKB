---
id: SYS-001
name: auth-service
environment: prod
criticality: critical
primary team: Identity & Access Team
support team: Platform / SRE
vendor: Internal Application
status: active
customer facing: yes
last updated: 2026-06-16
tags:
  - system
  - authentication
  - kubernetes
  - critical
  - prod
---

## System Overview

The auth-service is the centralized authentication and session management platform for the organization. It handles user login, token issuance (JWT), session lifecycle management, and credential validation for all customer-facing and internal applications.

- **What it does:** Authenticates users, issues and validates JWTs, manages active sessions
- **Why it exists:** Provides a single source of truth for identity verification across all services
- **Business process:** Customer authentication, session management, API authorization
- **Customer facing:** Yes — all login and authentication flows pass through this service

---

## Business Function

Customer authentication and identity management.

The auth-service enables:

- User login and logout for all customer-facing applications
- JWT issuance and validation for API authorization
- Session lifecycle management (creation, renewal, revocation)
- Credential rotation and secret management for downstream services

---

## Ownership & Support

### Primary Team

Identity & Access Team — responsible for day-to-day ownership, feature development, on-call rotation, and incident response.

### Support Team

Platform / SRE — secondary support during infrastructure-related incidents, Kubernetes issues, or database escalations.

### Vendor

Internal Application — fully developed and maintained in-house.

---

## Architecture Summary

- **Application type:** Microservice (stateless REST API)
- **Deployment model:** Kubernetes Deployment with HPA (Horizontal Pod Autoscaler)
- **Hosting platform:** Kubernetes (prod cluster)
- **Runtime technology:** JVM-based (Java/Spring Boot)
- **Namespace:** `auth`
- **Replicas:** 3 (minimum), scales to 6 under load

---

## Key Dependencies

### Internal Dependencies

- **auth-db** (PostgreSQL) — stores user credentials, sessions, and token metadata
- **api-gateway** — routes all authentication requests to auth-service
- **secrets management** — provides JWT signing keys and database credentials

### External Dependencies

- PostgreSQL Database (auth_db — 80M+ rows in sessions table)
- Kubernetes Secrets (JWT signing keys, DB credentials)
- PagerDuty (alerting)

---

## Interfaces

| Interface | Type | Direction | Description |
|-----------|------|-----------|-------------|
| `/login` | REST API | Inbound | User login endpoint |
| `/logout` | REST API | Inbound | Session termination |
| `/validate` | REST API | Inbound | Token validation for downstream services |
| `/health` | REST API | Inbound | Health check endpoint |
| auth-db | PostgreSQL | Outbound | Session and credential storage |
| api-gateway | HTTP | Inbound | All auth traffic routed through gateway |

---

## Environment Details

| Attribute | Value |
|-----------|-------|
| Kubernetes namespace | `auth` |
| Cluster | prod cluster |
| Region | Primary region |
| Container image | `registry.internal/auth-service` |
| Memory limit | 1Gi per pod |
| Statement timeout | 10s (database) |
| Session table size | ~80M rows |

---

## Monitoring & Alerting

| Monitor | Tool | Description |
|---------|------|-------------|
| `AuthService-CrashLoopBackOff` | PagerDuty | Fires when pods enter CrashLoopBackOff |
| `AuthService-DBTimeout` | PagerDuty | Fires when DB query P99 > threshold |
| DB query latency (P99) | Datadog | Tracks query performance |
| Pod restart count | Kubernetes metrics | Tracks container restarts |
| DB connection pool utilization | Grafana | Monitors connection exhaustion |
| Login success rate | Datadog | Tracks percentage of successful authentications |

---

## Common Failure Scenarios

| Failure Scenario | Related Incidents | Related Runbooks |
|------------------|-------------------|------------------|
| CrashLoopBackOff due to bad secret encoding | [[INC-003-k8s-crashloopbackoff-auth]] | [[RB-007-pod-crash-investigation]] |
| Database timeout from missing index | [[INC-008-db-timeout-auth-db]] | [[RB-005-database-timeout-connection-exhaustion]] |
| DB disk full on auth-db volume | [[INC-006-disk-full-db-volume]] | [[RB-003-disk-space-full]] |
| DB connection pool exhaustion | — | [[RB-005-database-timeout-connection-exhaustion]] |
| Pod OOM under load | — | [[RB-002-kubernetes-oom-remediation]] |

---

## Related Incidents

- [[INC-003-k8s-crashloopbackoff-auth]] — CrashLoopBackOff from bad config secret
- [[INC-008-db-timeout-auth-db]] — DB timeout from missing index after migration
- [[INC-006-disk-full-db-volume]] — Postgres disk full blocked auth-service writes

---

## Related Runbooks

- [[RB-005-database-timeout-connection-exhaustion]]
- [[RB-007-pod-crash-investigation]]
- [[RB-002-kubernetes-oom-remediation]]

---

## Escalation Information

| Trigger | Action | Channel |
|---------|--------|---------|
| Auth down > 10 min | Escalate to senior on-call + EM | PagerDuty |
| Login failure rate > 5% for 10 min | Escalate to DBA + senior on-call | PagerDuty |
| Secret rotation suspected as root cause | Engage secrets management team | #infra-secrets |
| SLA breach imminent (> 15 min outage) | Notify customer success for enterprise accounts | #customer-comms |
| Cannot resolve DB issue in 20 min | Page EM, evaluate read replica failover | #incident-response |

Governance references: [[Escalation Rules]], [[Guardrails]]

---

## Additional Notes

- The `sessions` table contains ~80M rows. Migrations against this table must be tested at production scale before executing in prod.
- JWT signing keys are stored as Kubernetes Secrets and rotated periodically. The rotation script must include base64 validation (see INC-003 post-mortem).
- `CASCADE` operations on the sessions table schema should be avoided — dependent indexes may be silently dropped.
- Enterprise SLA requires 99.9% uptime for authentication endpoints.

---
