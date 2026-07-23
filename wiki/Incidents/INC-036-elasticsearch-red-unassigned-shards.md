---
id: INC-036
title: Elasticsearch Cluster Red Due to Unassigned Shards
severity: SEV-2
service: logging
environment: prod
category: degradation
date: 2026-04-14
duration: "1h30m"
tags:
  - incident
  - elasticsearch
  - shards
  - cluster-health
  - logging
  - storage
error_family: unknown
resolution_runbook: RB-024
resolution_outcome: resolved
---

## Summary

The Elasticsearch logging cluster went to RED status after a data node ran out of disk (flood stage watermark hit). The node was excluded from allocation, leaving 24 primary shards unassigned. Log ingestion continued on healthy nodes but queries on affected indices returned partial results for 90 minutes.

## Symptoms

- `GET _cluster/health`: `status: red`, `unassigned_shards: 24`
- Kibana dashboards: "Results may be incomplete" warnings
- Elasticsearch logs: `[WARN] flood stage disk watermark exceeded on node es-data-03`
- Alert: `Elasticsearch-ClusterRed`
- Disk usage on es-data-03: 96.2% (flood stage: 95%)

## Diagnosis

1. Identified unassigned shards:
   ```bash
   curl -s localhost:9200/_cat/shards?v | grep UNASSIGNED
   # 24 primary shards, all were on es-data-03
   ```
2. Allocation explanation:
   ```bash
   curl -s localhost:9200/_cluster/allocation/explain | jq .
   # "the node is above the flood stage disk watermark"
   ```
3. es-data-03 had accumulated old indices (no ILM rollover for 30 days)
4. Disk grew from 70% to 96% over the last week

## Resolution

1. Freed disk by deleting old indices on the affected node:
   ```bash
   curl -X DELETE "localhost:9200/logs-2026.02.*"
   ```
2. Cleared the flood stage flag:
   ```bash
   curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d '{"transient":{"cluster.routing.allocation.disk.watermark.flood_stage":"97%"}}'
   ```
3. Triggered shard re-allocation:
   ```bash
   curl -X POST "localhost:9200/_cluster/reroute?retry_failed=true"
   ```
4. Verified cluster returned to GREEN:
   ```bash
   curl -s localhost:9200/_cluster/health | jq .status
   # "green"
   ```

## Post-Incident Review

- ILM policy was configured but rollover action was disabled accidentally 30 days ago
- Re-enabled ILM rollover and delete phases
- Added alert: disk usage > 80% on any ES data node
- Added alert: unassigned shards > 0 for more than 5 minutes
- Increased data node disk from 500GB to 1TB

## Links

- Related: [[RB-024-elasticsearch-cluster-recovery]]
