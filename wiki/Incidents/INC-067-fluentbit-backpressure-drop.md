---
id: INC-067
title: Fluent Bit Backpressure — Logs Dropped During Elasticsearch Slowdown
severity: SEV-3
service: logging-pipeline
environment: prod
category: degradation
date: 2026-06-12
duration: "2h"
tags:
  - incident
  - fluentbit
  - elasticsearch
  - logging
  - backpressure
  - observability
  - moderate
  - prod
---

## Summary

Elasticsearch ingestion slowed due to a large index merge, causing Fluent Bit's memory buffer to fill. Once the 64MB buffer limit was reached, Fluent Bit began dropping logs. Approximately 2 hours of logs from 40% of pods were lost, creating blind spots in debugging and audit trails.

## Symptoms

- Fluent Bit metrics: `fluentbit_output_dropped_records_total` climbing
- Kibana: log volume dropped 40% across multiple services
- Fluent Bit logs: `[warn] [engine] chunk '...' cannot be retried: buffer is full`
- Elasticsearch: index merge taking 45 minutes (normally <5 min)

## Diagnosis

1. Confirmed log drops
   ```bash
   kubectl logs -l app=fluent-bit -n logging --tail=50 | grep "buffer is full"
   # 240 occurrences in last 30 min
   ```

2. Elasticsearch slow merge
   ```bash
   curl -s http://elasticsearch:9200/_cat/thread_pool/force_merge?v
   # active: 1, queue: 12 (backlogged)
   ```

3. Fluent Bit buffer configured at 64MB with no filesystem buffer fallback

## Resolution

1. **Mitigate:** Reduced Elasticsearch merge pressure by throttling
   ```bash
   curl -X PUT http://elasticsearch:9200/_cluster/settings -H 'Content-Type: application/json' \
     -d '{"transient":{"indices.store.throttle.max_bytes_per_sec":"200mb"}}'
   ```

2. **Fix:** Enabled Fluent Bit filesystem buffering (spill to disk when memory full)

3. **Verify:** Log ingestion rate recovered, no more drops

## Post-Incident Review

- In-memory-only buffering guarantees log loss during destination slowdowns
- Enabled Fluent Bit filesystem buffer (storage.type: filesystem, 1GB limit)
- Added alert: if `fluentbit_output_dropped_records_total` increases by >0
- Elasticsearch: scheduled large merges during off-peak hours only

## Links

- Runbooks: [[RB-015-observability-pipeline-recovery]]
- Related incidents: [[INC-005-disk-full-logs-node01]]
