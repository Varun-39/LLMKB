---
id: RB-024
title: Elasticsearch / OpenSearch Cluster Recovery
service: elasticsearch
related_services:
  - logging-pipeline
  - search-api
  - kibana
severity: SEV-2
environment: prod
category: resource-exhaustion
risk_level: high
estimated_duration: "30m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - elasticsearch
  - opensearch
  - cluster
  - shards
  - search
  - prod
related_incidents:
  - "[[INC-036-elasticsearch-red-unassigned-shards]]"
  - "[[INC-072-opensearch-snapshot-failure-repo-readonly]]"
related_runbooks:
  - "[[RB-003-disk-space-full]]"
  - "[[RB-015-observability-pipeline-recovery]]"
related_guardrails: []
---

## Purpose

Diagnose and recover from Elasticsearch/OpenSearch cluster issues including red/yellow status, unassigned shards, node failures, and disk watermark breaches.

**Desired outcome:** Cluster status GREEN, all shards assigned, search and indexing operations functioning normally.

## Success Criteria

- `_cluster/health` shows `status: green`
- Unassigned shards: 0
- All data nodes joined and healthy
- Search latency at baseline
- Indexing rate at baseline (no backlog)

## Scope

| Attribute | Value |
|-----------|-------|
| Service | elasticsearch/opensearch |
| Related services | logging-pipeline, search-api, kibana |
| Environments | prod, staging |
| Use when | Cluster status RED/YELLOW, unassigned shards, node failures |
| Do NOT use when | Slow queries only (index optimization issue, not cluster health) |
| Risk level | High (wrong shard operations can cause data loss) |
| Estimated duration | 25–30 minutes |
| Approval required | No |

## Prerequisites

- [ ] `curl` access to Elasticsearch API
- [ ] Knowledge of cluster topology (nodes, roles)
- [ ] Access to node-level metrics (disk, memory)

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `curl` | Elasticsearch REST API | Admin |
| `kubectl` | Pod operations for ES nodes | Cluster admin |
| Grafana/Kibana | Cluster monitoring | Read access |

## Trigger

- Alert: `*-ElasticsearchRed`, `*-UnassignedShards`
- Symptom: Search queries returning errors or incomplete results
- Symptom: Log ingestion pipeline backed up
- Metric: Cluster status yellow or red on monitoring dashboard

## Triage

1. Check cluster health
   ```bash
   curl -s http://elasticsearch:9200/_cluster/health | jq '{status, number_of_nodes, unassigned_shards, active_shards_percent_as_number}'
   ```

2. Check which indices are affected
   ```bash
   curl -s http://elasticsearch:9200/_cat/indices?v&health=red
   curl -s http://elasticsearch:9200/_cat/indices?v&health=yellow
   ```

3. Check node status
   ```bash
   curl -s http://elasticsearch:9200/_cat/nodes?v&h=name,heap.percent,disk.used_percent,node.role
   ```

## Investigation

1. **Identify reason for unassigned shards**
   ```bash
   curl -s http://elasticsearch:9200/_cluster/allocation/explain | jq '.allocate_explanation'
   ```

2. **Check disk watermarks**
   ```bash
   curl -s http://elasticsearch:9200/_cat/allocation?v
   # What to look for: disk.percent >85% = watermark breached
   ```

3. **Check for failed nodes**
   ```bash
   curl -s http://elasticsearch:9200/_cat/nodes?v
   # Compare with expected node count
   ```

4. **Decision point:**
   - IF disk watermark breached → proceed to Mitigation Option A
   - IF node failed → proceed to Mitigation Option B
   - IF shard allocation blocked → proceed to Mitigation Option C
   - IF index corrupted → proceed to Mitigation Option D

## Mitigation

### Option A: Free disk space (watermark breach)

```bash
# Delete old indices:
curl -X DELETE http://elasticsearch:9200/logs-2026.05.*
# Or increase watermark temporarily:
curl -X PUT http://elasticsearch:9200/_cluster/settings -H 'Content-Type: application/json' \
  -d '{"transient":{"cluster.routing.allocation.disk.watermark.high":"95%"}}'
```

### Option B: Node failed — restart or replace

```bash
kubectl delete pod elasticsearch-data-2 -n logging
# StatefulSet will recreate. Shards will reassign.
```

### Option C: Unblock shard allocation

```bash
# If allocation was disabled (maintenance left on):
curl -X PUT http://elasticsearch:9200/_cluster/settings -H 'Content-Type: application/json' \
  -d '{"transient":{"cluster.routing.allocation.enable":"all"}}'
# Retry failed allocations:
curl -X POST http://elasticsearch:9200/_cluster/reroute?retry_failed=true
```

### Option D: Delete corrupted index (data loss)

```bash
# Last resort — recreate from source:
curl -X DELETE http://elasticsearch:9200/<corrupted-index>
# Re-index from source data
```

**After mitigation:** Wait for shard relocation to complete (can take minutes to hours depending on data size).

## Verification

- [ ] `_cluster/health` status: green
- [ ] Unassigned shards: 0
- [ ] All nodes present
- [ ] Search queries returning results
- [ ] Indexing rate at baseline

```bash
curl -s http://elasticsearch:9200/_cluster/health | jq '.status'
# Expected: "green"
curl -s http://elasticsearch:9200/_cat/shards?v | grep -c UNASSIGNED
# Expected: 0
```

## Failure Signals

- Shards won't assign despite allocation enabled
- Node keeps crashing after restart
- Disk watermark cannot be freed (no deletable data)
- Cluster stays yellow after hours (replica can't be placed)

**If any failure signal is present:** Escalate.

## Rollback

1. **If wrong index deleted:** Restore from snapshot
2. **If watermark change too aggressive:** Revert cluster settings
3. **If reroute caused imbalance:** Wait for automatic rebalancing

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Cluster RED for >15 min | Data platform team | PagerDuty | 10 min |
| Data loss suspected | EM + data team | #incident-response | Immediate |
| Multiple nodes down | Platform team | #platform-support | 10 min |
| Snapshot restore needed | DBA/data team | #data-eng | 15 min |

## Notes

- **RED = at least one primary shard unassigned.** Data loss is possible. Prioritize restoring primaries.
- **YELLOW = replicas unassigned.** Data is safe but not redundant. Less urgent but fix before next node failure.
- **Never force-allocate a stale shard** unless you accept potential data loss. Use `_cluster/reroute` with `accept_data_loss: true` only as last resort.
- **Disk watermarks:** flood_stage=95% (makes index read-only), high=90% (stops allocation), low=85% (starts relocation).

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Stop an ES data node in staging, verify shard reassignment and recovery.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Data Platform Team | Initial publication |
