---
title: Category Navigation
tags:
  - index
  - navigation
created: 2026-06-02
updated: 2026-06-02
type: index
---

## Category Navigation

Browse incidents and runbooks by category, service, or tag. Use this page when you know the type of problem but not the specific note name.

---

## By Problem Category

### Kubernetes / Container

Issues involving pod scheduling, image pulling, node health, OOMKilled, CrashLoopBackOff, or ephemeral storage.

```dataview
TABLE title AS "Note", severity AS "Sev", file.folder AS "Type", date AS "Date"
FROM "Incidents" OR "Runbooks"
WHERE contains(tags, "kubernetes") OR contains(tags, "container") OR contains(tags, "node") OR contains(tags, "kubelet")
SORT date DESC
```

---

### Infrastructure / Resource

Disk exhaustion, inode limits, memory pressure, NIC saturation, high CPU on nodes.

```dataview
TABLE title AS "Note", severity AS "Sev", file.folder AS "Type", date AS "Date"
FROM "Incidents" OR "Runbooks"
WHERE contains(tags, "disk") OR contains(tags, "cpu") OR contains(tags, "infra") OR contains(tags, "inode") OR contains(tags, "network") OR contains(tags, "nic")
SORT date DESC
```

---

### Database

Timeouts, connection pool exhaustion, lock contention, slow queries, replica lag, disk on DB volumes.

```dataview
TABLE title AS "Note", severity AS "Sev", file.folder AS "Type", date AS "Date"
FROM "Incidents" OR "Runbooks"
WHERE contains(tags, "database") OR contains(tags, "postgres") OR contains(tags, "connection-pool") OR contains(tags, "replication")
SORT date DESC
```

---

### Deployment / Application

Failed deployments, bad config rollouts, feature flag issues, canary failures, rollback problems.

```dataview
TABLE title AS "Note", severity AS "Sev", file.folder AS "Type", date AS "Date"
FROM "Incidents" OR "Runbooks"
WHERE contains(tags, "deployment") OR contains(tags, "config") OR contains(tags, "feature-flag") OR contains(tags, "canary") OR contains(tags, "rollback")
SORT date DESC
```

---

## By Service

### payment-gateway / payment-service

```dataview
TABLE title AS "Note", severity AS "Sev", status AS "Status", date AS "Date"
FROM "Incidents"
WHERE service = "payment-gateway" OR service = "payment-service"
SORT date DESC
```

### auth-service

```dataview
TABLE title AS "Note", severity AS "Sev", status AS "Status", date AS "Date"
FROM "Incidents"
WHERE service = "auth-service"
SORT date DESC
```

### api-gateway

```dataview
TABLE title AS "Note", severity AS "Sev", status AS "Status", date AS "Date"
FROM "Incidents"
WHERE service = "api-gateway"
SORT date DESC
```

### reporting-service / notifications-service

```dataview
TABLE title AS "Note", severity AS "Sev", status AS "Status", date AS "Date"
FROM "Incidents"
WHERE service = "reporting-service" OR service = "notifications-service"
SORT date DESC
```

---

## By Severity

```dataview
TABLE title AS "Title", service AS "Service", date AS "Date", status AS "Status"
FROM "Incidents"
SORT severity ASC, date DESC
```

---

## Tag Cloud Reference

| Tag | Meaning |
|-----|---------|
| `kubernetes` | Pod, node, or cluster-level issue |
| `container` | Container lifecycle (pull, runtime) |
| `oom` | Out-of-memory kill event |
| `crashloop` | Pod restart loop |
| `node` | Node-level failure or condition |
| `disk` | Disk space or filesystem issue |
| `inode` | Inode exhaustion |
| `cpu` | CPU saturation or throttling |
| `memory` | Memory pressure |
| `infra` | Infrastructure/OS-level problem |
| `network` | NIC or network throughput issue |
| `database` | Any DB-layer incident |
| `postgres` | Postgres-specific |
| `timeout` | Query or connection timeout |
| `connection-pool` | DB connection pool exhaustion |
| `replication` | Replica lag or sync issue |
| `lock-contention` | DB table/row lock blocking |
| `deployment` | Release, rollout, or rollback issue |
| `config` | Configuration error |
| `feature-flag` | Feature flag misconfiguration |
| `canary` | Canary release failure |
| `rollback` | Failed or partial rollback |
| `critical` | Severity tag for SEV-1 |
| `high` | Severity tag for SEV-2 |
| `medium` | Severity tag for SEV-3 |
| `prod` | Occurred in production |
| `staging` | Occurred in staging |

---

## Quick Links

- [[Incident Index]] — Full table of all incidents
- [[Runbook Index]] — All runbooks by service
- [[Production Support Wiki]] — Home
