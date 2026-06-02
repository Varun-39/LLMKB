---
title: Cross-Link Map
tags:
  - index
  - navigation
  - backlinks
created: 2026-06-02
updated: 2026-06-02
type: index
---

## Cross-Link Map

This page documents how incidents and runbooks connect to each other. Use it to trace recurring patterns, identify frequently-used runbooks, and find clusters of related problems.

For a visual version, open the Obsidian Graph View and filter by `#incident` or `#runbook`.

---

## Incident → Runbook Map

Each incident references the runbook used to resolve it. Runbooks with many inbound links are high-value documentation targets.

```dataview
TABLE
  title AS "Incident",
  severity AS "Sev",
  related_runbooks AS "Runbooks Used"
FROM "Incidents"
WHERE related_runbooks
SORT severity ASC, date DESC
```

---

## Incident → Related Incident Map

Incidents that reference other incidents — useful for spotting recurring failures or cascading effects.

```dataview
TABLE
  title AS "Incident",
  service AS "Service",
  related_incidents AS "Related Incidents"
FROM "Incidents"
WHERE related_incidents
SORT date DESC
```

---

## Runbook → Incident Map

Each runbook references the incidents where it was exercised. Runbooks with no related incidents have never been used in production.

```dataview
TABLE
  title AS "Runbook",
  service AS "Service",
  related_incidents AS "Incidents"
FROM "Runbooks"
SORT last-updated DESC
```

---

## Manually Maintained: Key Incident Clusters

These clusters highlight recurring failure patterns across the incident history. Update after each post-mortem.

### OOM / Memory Pressure

Recurring pattern: services without bounded caches or proper memory requests repeatedly exhaust heap or node memory.

| Incident | Service | Root Cause |
|----------|---------|------------|
| [[INC-001-payment-service-oom-crash]] | payment-gateway | Unbounded idempotency cache |
| [[INC-002-k8s-oom-api-pod]] | api-gateway | Unbounded response cache |
| [[INC-016-memory-pressure-app-node]] | api-gateway (node) | Over-packed node, low kubelet eviction threshold |

Runbook: [[RB-001-kubernetes-oom]]

---

### Disk / Storage Exhaustion

Disk issues appear across three distinct layers: application log volumes, DB data volumes, and node ephemeral storage.

| Incident | Layer | Root Cause |
|----------|-------|------------|
| [[INC-005-disk-full-logs-node01]] | Log node | Debug log level in prod |
| [[INC-006-disk-full-db-volume]] | Postgres volume | WAL accumulation + dead tuple bloat |
| [[INC-014-k8s-node-disk-pressure]] | Node ephemeral storage | Debug container image in prod |
| [[INC-015-inode-exhaustion-var-log]] | Application filesystem | Orphaned lock files in temp dir |

Runbook: [[RB-002-disk-space-full]]

---

### Database Failures

DB failures cluster into three sub-types: query timeouts, connection exhaustion, and write blocking.

| Incident | Sub-type | Root Cause |
|----------|----------|------------|
| [[INC-008-db-timeout-auth-db]] | Timeout | Missing index after migration |
| [[INC-009-db-connection-pool-exhausted]] | Pool exhaustion | Connection leak in async code |
| [[INC-017-db-read-replica-lag]] | Replica lag | Backfill during business hours |
| [[INC-018-db-lock-contention-payments]] | Lock contention | ALTER TABLE during peak traffic |
| [[INC-006-disk-full-db-volume]] | Disk full | WAL accumulation on data volume |

Runbook: [[RB-004-db-timeouts]]

---

### Deployment / Config Failures

Every deployment incident traces to a missing gate: schema validation, migration planning, or flag approval.

| Incident | Type | Root Cause |
|----------|------|------------|
| [[INC-010-release-failed-canary-api]] | Canary | ConfigMap schema mismatch |
| [[INC-011-rollback-failed-frontend]] | Rollback | DB migration not reverted |
| [[INC-019-broken-feature-flag-auth]] | Feature flag | Flag enabled prematurely in prod |
| [[INC-020-bad-config-rollout-payment]] | Config error | Rate limit set to 0 |

Runbook: [[RB-005-failed-deployment]]

---

### Kubernetes Scheduling / Node Health

| Incident | Type | Root Cause |
|----------|------|------------|
| [[INC-003-k8s-crashloopbackoff-auth]] | CrashLoopBackOff | Malformed base64 secret |
| [[INC-004-k8s-node-notready]] | Node NotReady | Kubelet OOM-killed |
| [[INC-012-k8s-imagepullbackoff-reports]] | ImagePullBackOff | Expired ECR credentials |
| [[INC-013-k8s-pending-pods-resource-pressure]] | Pending pods | Cluster CPU exhausted by uncapped batch job |
| [[INC-014-k8s-node-disk-pressure]] | DiskPressure | Container logs filling ephemeral storage |

Runbook: [[RB-006-pod-crash]]

---

## Runbook Coverage

All runbooks are now created and linked from the incident library.

| Runbook | Incidents Using It | Status |
|---------|-------------------|--------|
| [[RB-001-payment-gateway-oom-recovery]] | INC-001 | ✅ Active |
| [[RB-002-kubernetes-oom-remediation]] | INC-001, INC-002, INC-016 | ✅ Active |
| [[RB-003-disk-space-full]] | INC-005, INC-006, INC-014, INC-015 | ✅ Active |
| [[RB-004-high-cpu-usage]] | INC-007, INC-013, INC-021 | ✅ Active |
| [[RB-005-database-timeout-connection-exhaustion]] | INC-006, INC-008, INC-009, INC-011, INC-017, INC-018 | ✅ Active |
| [[RB-006-failed-deployment-rollback]] | INC-010, INC-011, INC-012, INC-019, INC-020 | ✅ Active |
| [[RB-007-pod-crash-investigation]] | INC-003, INC-004, INC-012, INC-013, INC-014, INC-016 | ✅ Active |

---

## Navigation

- [[Incident Index]] — Table view of all incidents
- [[Runbook Index]] — All runbooks by service
- [[Category Navigation]] — Browse by problem type or service
- [[Production Support Wiki]] — Home
