---
id: INC-087
title: Elasticsearch Dynamic Mapping Explosion Caused Cluster Instability
severity: SEV-2
service: reporting-service
environment: prod
category: degradation
date: 2026-04-15
duration: "1h 20m"
tags:
  - incident
  - elasticsearch
  - mapping
  - dynamic-mapping
  - cluster
  - reporting-service
  - prod
error_family: unknown
resolution_runbook: RB-024
resolution_outcome: resolved
---

## Summary

A new event payload format introduced arbitrary key names in a JSON field that Elasticsearch was indexing with `dynamic: true`. Within 4 hours of deployment, the index mapping accumulated 52,000 fields — far exceeding the `index.mapping.total_fields.limit` of 1,000 — causing Elasticsearch to reject new document indexing, making logs and search unavailable for 1 hour 20 minutes.

## Symptoms

- Elasticsearch logs: `Limit of total fields [1000] has been exceeded`
- Kibana: log search returning no new results for past 4 hours
- reporting-service bulk index API: returning 400 errors
- Alerting pipeline (relies on ES log search): no alerts firing during window

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All internal analytics and observability users |
| Services degraded | Elasticsearch, Kibana, reporting-service log search |
| Revenue impact | N/A (internal tooling) |
| Duration | 09:30 → 10:50 UTC (1h 20m) |
| Data loss | ~4 hours of log data not indexed (available in raw object storage) |
| SLA breach | No (internal service) |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 05:30 | New event format deployed |
| 06:00 | Dynamic mapping begins accumulating fields |
| 09:30 | Field limit reached; indexing fails |
| 09:35 | Kibana alert: "No data" |
| 09:45 | On-call began investigation |
| 10:20 | Index reindexed with explicit mapping |
| 10:50 | Full indexing resumed |

## Diagnosis

1. Checked ES cluster health:
   ```bash
   curl http://es-master:9200/_cluster/health?pretty
   # status: yellow, unassigned_shards: 0 (healthy but rejecting writes)
   ```
2. Checked index mapping field count:
   ```bash
   curl http://es-master:9200/logs-prod/_mapping | jq '[.. | objects | keys] | flatten | length'
   # 52341
   ```
3. Found dynamic mapping on events.payload:
   ```bash
   curl http://es-master:9200/logs-prod/_mapping | jq '.logs-prod.mappings.properties.events.properties.payload'
   # dynamic: true  — 51,000 fields accumulated here
   ```

## Resolution

1. **Mitigate:** Created new index with explicit mapping (payload as `object, dynamic: false`)
   ```bash
   curl -X PUT http://es-master:9200/logs-prod-v2 -H 'Content-Type: application/json' -d @mapping-v2.json
   ```
2. **Reindexed from raw source:**
   ```bash
   curl -X POST http://es-master:9200/_reindex -d '{"source":{"index":"logs-prod"},"dest":{"index":"logs-prod-v2"}}'
   ```
3. **Updated alias to point to new index:**
   ```bash
   curl -X POST http://es-master:9200/_aliases -d '{"actions":[{"remove":{"index":"logs-prod","alias":"logs"}},{"add":{"index":"logs-prod-v2","alias":"logs"}}]}'
   ```
4. **Fixed event payload field** in reporting-service to flatten keys before indexing

## Post-Incident Review

**What went well:**
- Raw log data was available in S3; no permanent data loss

**What needs improvement:**
- `dynamic: true` allowed in production index
- No alert on mapping field count growth

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Set `dynamic: false` on all payload/metadata fields in ES index templates | Platform | 2026-04-22 | Open |
| Add alert: ES index field count > 800 | Observability | 2026-04-22 | Open |

## Links

- Runbooks: [[RB-024-elasticsearch-cluster-recovery]]
- Related incidents: [[INC-036-elasticsearch-red-unassigned-shards]]
