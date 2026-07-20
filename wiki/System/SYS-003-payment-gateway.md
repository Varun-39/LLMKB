---
id: SYS-003
name: payment-gateway
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
  - jvm
  - critical
  - prod
---

## System Overview

The payment-gateway is the customer-facing transaction processing service responsible for handling payment requests through the `/api/v2/payments/process` endpoint. It runs on the JVM within a memory-constrained Kubernetes deployment and has a history of OOM-related failures.

- **What it does:** Processes payment transactions at the gateway layer
- **Why it exists:** Provides the entry point for payment processing requests
- **Business process:** Payment transaction processing
- **Customer facing:** Yes — direct transaction processing path

---

## Business Function

Payment processing (gateway/transaction layer).

The payment-gateway enables:

- Processing of payment transactions via `/api/v2/payments/process`
- Routing transactions to the payment-processor
- Front-line transaction handling for the payments platform

---

## Ownership & Support

### Primary Team

Payments Team — service owner Priya Sharma (per runbook RB-001).

### Support Team

Platform / SRE — engaged for node-level resource exhaustion and Kubernetes issues.

### Vendor

Internal Application — developed and maintained in-house.

---

## Architecture Summary

- **Application type:** Microservice (REST API)
- **Deployment model:** Kubernetes Deployment
- **Hosting platform:** Kubernetes (prod cluster), nodes `c5.xlarge` (8Gi total)
- **Runtime technology:** JVM — configured `-Xmx768m` inside a 1Gi container
- **Namespace:** `payments`
- **Container image:** `registry.internal/payment-gateway`

---

## Key Dependencies

### Internal Dependencies

- **[[SYS-004-api-gateway]]** — upstream routing
- **payment-processor** — downstream transaction processor

### External Dependencies

- AWS ECR (container image registry)
- PagerDuty (alerting)
- Grafana (resource dashboards)

---

## Interfaces

| Interface | Type | Direction | Description |
|-----------|------|-----------|-------------|
| `/api/v2/payments/process` | REST API | Inbound | Payment processing endpoint |
| `/health` | REST API | Inbound | Health check endpoint |
| api-gateway | HTTP | Inbound | Upstream request routing |
| payment-processor | HTTP | Outbound | Downstream transaction processing |

---

## Environment Details

| Attribute | Value |
|-----------|-------|
| Kubernetes namespace | `payments` |
| Cluster | prod cluster |
| Node type | `c5.xlarge` (8Gi total) |
| Container memory limit | 1Gi (JVM `-Xmx768m`) |
| Container image | `registry.internal/payment-gateway` |

---

## Monitoring & Alerting

| Monitor | Tool | Description |
|---------|------|-------------|
| `PaymentGateway-PodCrashLooping` | PagerDuty | Fires on pod crash loops |
| `PaymentGateway-MemoryUsageHigh` | PagerDuty | Fires when memory > 85% for 5 min |
| Memory / CPU trends | Grafana (`Payment Gateway - Resources`) | Resource usage dashboard |
| Transaction success rate | Grafana | Tracks processing success |

---

## Common Failure Scenarios

| Failure Scenario | Related Incidents | Related Runbooks |
|------------------|-------------------|------------------|
| JVM memory exhaustion / OOMKilled | [[INC-001-payment-service-oom-crash]] | [[RB-001-payment-gateway-oom-recovery]] |
| Pod crash / CrashLoopBackOff | — | [[RB-007-pod-crash-investigation]] |
| Kubernetes-level OOM | — | [[RB-002-kubernetes-oom-remediation]] |
| High CPU saturation | — | [[RB-004-high-cpu-usage]] |

---

## Related Incidents

- [[INC-001-payment-service-oom-crash]] — OOM crash in payment processing

---

## Related Runbooks

- [[RB-001-payment-gateway-oom-recovery]]
- [[RB-002-kubernetes-oom-remediation]]
- [[RB-007-pod-crash-investigation]]
- [[RB-004-high-cpu-usage]]

---

## Escalation Information

| Trigger | Action | Channel |
|---------|--------|---------|
| Still crashing after memory bump + restart | Senior on-call + Platform | #incident-response |
| No resolution in 30 min | Engineering Manager | PagerDuty escalation |
| Leak confirmed, no hotfix available | Service owner (Priya Sharma) | Direct page |
| Node-level resource exhaustion | Platform / SRE | #platform-support |

Governance references: [[Escalation Rules]], [[Guardrails]]

---

## Additional Notes

- JVM configured `-Xmx768m` inside a 1Gi container — the gap covers off-heap and metaspace.
- If raising the memory limit above 2Gi, verify node capacity — pods run on `c5.xlarge` (8Gi total).
- Historical: 3 of 4 past OOM incidents traced to unbounded caches. Check cache sizes first.
- Note: "payment-gateway" (this gateway/processing layer) is distinct from [[SYS-002-payment-service]] (the payment initiation/persistence service).

---
