---
id:
name:
environment:
criticality:
primary team:
support team:
vendor:
status:
customer facing:
last updated:
tags:
---


## System Overview

High-level description of the system and its business purpose.

This section should explain:

- What the system does
- Why it exists
- Which business process it supports
- Whether it is customer-facing or internal

A reader unfamiliar with the platform should understand the system's role after reading this section.

---

## Business Function

Describe the business capability provided by the system.

Examples:

- Payment processing
- Trade finance processing
- Customer authentication
- Regulatory reporting

Focus on business value rather than technical implementation.

---

## Ownership & Support

### Primary Team

Team responsible for day-to-day ownership, support and maintenance.

### Support Team

Secondary support team involved during incidents or escalations.

### Vendor

External vendor or product owner if applicable.

If internally developed, state "Internal Application".

---

## Architecture Summary

Describe the major components that make up the system.

Include:

- Application type
- Deployment model
- Hosting platform
- Runtime technology

Avoid excessive technical detail.

The goal is to provide context for responders.

---

## Key Dependencies

List systems, platforms or services required for normal operation.

Examples:

- Databases
- Message queues
- APIs
- Authentication services
- External vendors

Use wikilinks whenever dependency documentation exists.

### Internal Dependencies

- SYS-XXX

### External Dependencies

- Oracle Database
- SWIFT Network
- Vendor API

---

## Interfaces

Describe how the system communicates with other systems.

Examples:

- REST APIs
- Kafka Topics
- IBM MQ Queues
- Database Connections
- File Transfers

Include only major interfaces.

---

## Environment Details

Describe important deployment information.

Examples:

- Kubernetes namespace
- Cluster
- Region
- Data centre
- Production environment

This section should contain operational information commonly required during investigations.

---

## Monitoring & Alerting

Describe how the system is monitored.

Examples:

- Prometheus metrics
- Grafana dashboards
- Splunk searches
- Alert rules

Include links if available.

---

## Common Failure Scenarios

List common issues known to affect this system.

Examples:

- JVM memory exhaustion
- Database connection pool exhaustion
- Kafka consumer lag
- Pod restart loops

Each issue should link to related incidents and runbooks where possible.

| Failure Scenario    | Related Incidents | Related Runbooks |
| ------------------- | ----------------- | ---------------- |
| JVM Heap Exhaustion | INC-001           | RB-001           |

---

## Related Incidents

Link incidents where this system was directly affected.

This section creates a historical record of operational issues associated with the system.

- INC-001
- INC-004

---

## Related Runbooks

Link runbooks commonly used when supporting this system.

- RB-001
- RB-003

---

## Escalation Information

Describe when and how the system should be escalated.

Include:

- Escalation triggers
- Support channels
- Responsible teams
- Guardrails

Reference governance documents when applicable.

---

## Additional Notes

Any information that does not fit elsewhere but may assist responders, support teams or future documentation efforts.

---