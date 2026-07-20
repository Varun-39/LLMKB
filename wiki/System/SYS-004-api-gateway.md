---
id: SYS-004
name: api-gateway
environment: prod
criticality: critical
primary team: Platform Team
support team: Platform / SRE
vendor: Internal Application
status: active
customer facing: yes
last updated: 2026-06-16
tags:
  - system
  - gateway
  - edge
  - kubernetes
  - critical
  - prod
---

## System Overview

The api-gateway is the edge routing layer that fronts the platform's backend services. All authenticated API traffic passes through it, and it depends on auth-service for token validation. When auth-service is unavailable, the api-gateway returns 401s for authenticated endpoints, making it a key system in the blast radius of upstream failures.

- **What it does:** Routes and authorizes inbound API traffic to backend services
- **Why it exists:** Provides a single, controlled entry point for all API requests
- **Business process:** API routing, authentication enforcement, traffic management
- **Customer facing:** Yes — the entry point for customer and client API traffic

---

## Business Function

API routing and edge authorization.

The api-gateway enables:

- Routing requests to backend services (auth-service, payment-service, etc.)
- Enforcing authentication on protected endpoints
- Serving as the controlled ingress point for the platform

---

## Ownership & Support

### Primary Team

Platform Team — owns the edge/gateway layer.

### Support Team

Platform / SRE — engaged for routing, capacity, and node-level issues.

### Vendor

Internal Application — developed and maintained in-house.

---

## Architecture Summary

- **Application type:** Edge gateway / reverse proxy (REST)
- **Deployment model:** Kubernetes Deployment
- **Hosting platform:** Kubernetes (prod cluster)
- **Runtime technology:** Service-mesh / gateway layer fronting backend microservices

---

## Key Dependencies

### Internal Dependencies

- **[[SYS-001-auth-service]]** — token validation for authenticated endpoints
- **[[SYS-002-payment-service]]** — routes payment requests
- **[[SYS-003-payment-gateway]]** — routes payment processing requests
- **reporting-service** — routes reporting requests

### External Dependencies

- PagerDuty (alerting)
- Grafana / Datadog (metrics)

---

## Interfaces

| Interface | Type | Direction | Description |
|-----------|------|-----------|-------------|
| Public API endpoints | REST / HTTP | Inbound | Client and customer traffic ingress |
| auth-service | HTTP | Outbound | Token validation |
| Backend services | HTTP | Outbound | Request routing to payment, reporting, etc. |
| `/health` | REST API | Inbound | Health check endpoint |

---

## Environment Details

| Attribute | Value |
|-----------|-------|
| Cluster | prod cluster |
| Role | Edge / ingress routing layer |
| Auth dependency | auth-service (`/validate`) |

---

## Monitoring & Alerting

| Monitor | Tool | Description |
|---------|------|-------------|
| `*-HighCPU` / `*-HighLatency` | PagerDuty | CPU/latency saturation alerts |
| `*-CanaryErrorRate` | PagerDuty | Canary release error rate |
| Request error rate (4xx/5xx) | Grafana | Downstream 401 spikes when auth-service is down |
| P99 latency | Grafana | Edge routing latency |

---

## Common Failure Scenarios

| Failure Scenario | Related Incidents | Related Runbooks |
|------------------|-------------------|------------------|
| Downstream 401s when auth-service is down | [[INC-003-k8s-crashloopbackoff-auth]] | [[RB-007-pod-crash-investigation]] |
| Canary / release failure | [[INC-010-release-failed-canary-api]] | [[RB-006-failed-deployment-rollback]] |
| NIC saturation on API node | [[INC-021-nic-saturation-api-node]] | [[RB-004-high-cpu-usage]] |
| High CPU saturation | — | [[RB-004-high-cpu-usage]] |
| Pod crash / CrashLoopBackOff | — | [[RB-007-pod-crash-investigation]] |

---

## Related Incidents

- [[INC-003-k8s-crashloopbackoff-auth]] — returned 401s downstream during auth outage
- [[INC-010-release-failed-canary-api]] — failed canary release
- [[INC-021-nic-saturation-api-node]] — NIC saturation on API node

---

## Related Runbooks

- [[RB-006-failed-deployment-rollback]]
- [[RB-004-high-cpu-usage]]
- [[RB-007-pod-crash-investigation]]

---

## Escalation Information

| Trigger | Action | Channel |
|---------|--------|---------|
| Node-level CPU at 100% affecting multiple services | Platform / SRE team | #platform-support |
| Rollback does not reduce error rate within 10 min | Senior on-call + service owner | PagerDuty |
| Image pull failing cluster-wide | Platform team | #platform-support |
| Customer-facing SEV-1 with no fix in 20 min | Engineering Manager + IC | #incident-response |

Governance references: [[Escalation Rules]], [[Guardrails]]

---

## Additional Notes

- The api-gateway sits in the blast radius of auth-service: when auth-service fails, the gateway returns 401s for all authenticated endpoints (see INC-003).
- ConfigMap schema mismatches are a common cause of canary failures in this environment (see INC-010).
- NIC saturation can present as CPU saturation — check network metrics when CPU profiling shows threads in I/O wait (see INC-021).

---
