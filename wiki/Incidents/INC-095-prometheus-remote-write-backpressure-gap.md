---
id: INC-095
title: Prometheus Remote Write Backpressure Created 4-Hour Metric Gap
severity: SEV-3
service: general
environment: prod
category: degradation
date: 2026-05-01
duration: "4h 15m"
tags:
  - incident
  - prometheus
  - remote-write
  - metrics
  - observability
  - prod
error_family: unknown
resolution_runbook: RB-015
resolution_outcome: resolved
---

## Summary

Prometheus remote write to the long-term storage backend (Thanos) fell behind during a metric cardinality spike (new high-cardinality label introduced in auth-service). The remote write queue filled up and Prometheus began dropping samples rather than blocking, resulting in a 4-hour gap in all metric data in Thanos. Dashboards showed no data; alerts based on Thanos queries silently stopped firing.

## Symptoms

- Grafana: all dashboards showing "No data" for past 4 hours
- Prometheus UI: `prometheus_remote_storage_samples_dropped_total` rising
- Remote write queue: `prometheus_remote_storage_queue_highest_sent_timestamp` lagging 4 hours
- Thanos query: returning no data for the window
- Alert silence: 3 expected alerts did not fire during the window

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | SRE and engineering teams (no operational visibility) |
| Services degraded | Observability stack (metrics pipeline only) |
| Revenue impact | N/A (indirect risk — silent alert gap) |
| Duration | 08:00 → 12:15 UTC (4h 15m) |
| Data loss | ~4h of metric samples dropped (Prometheus local TSDB retained data but not shipped to Thanos) |
| SLA breach | No |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 08:00 | auth-service deployed with high-cardinality label (user_id in metric) |
| 08:05 | Prometheus ingestion rate doubles; remote write queue fills |
| 08:10 | Prometheus begins dropping remote write samples |
| 10:30 | Engineer notices Grafana showing no data |
| 11:00 | Root cause identified: cardinality spike + queue drop |
| 12:15 | Cardinality reduced; queue draining resumed |

## Diagnosis

1. Checked dropped samples:
   ```bash
   curl http://prometheus:9090/api/v1/query?query=prometheus_remote_storage_samples_dropped_total
   # 4,200,000 samples dropped
   ```
2. Found cardinality spike:
   ```bash
   curl http://prometheus:9090/api/v1/query?query=prometheus_tsdb_head_series
   # 2,800,000 active series (normal: 320,000)
   ```
3. Identified culprit metric:
   ```bash
   curl http://prometheus:9090/api/v1/query?query=topk(5,count+by+(__name__)+({__name__=~".+"}))'
   # auth_request_total{user_id="..."}: 2,450,000 series
   ```

## Resolution

1. **Mitigate:** Dropped the high-cardinality metric at Prometheus scrape level:
   ```yaml
   # prometheus.yml metric_relabel_configs
   - source_labels: [__name__]
     regex: auth_request_total
     action: drop
   ```
2. **Reloaded Prometheus config:**
   ```bash
   curl -X POST http://prometheus:9090/-/reload
   ```
3. **Cardinality dropped** to 340,000 series within 5 minutes
4. Remote write queue began draining; Thanos receiving data again
5. **Fix:** Removed `user_id` label from auth_request_total metric in auth-service code

## Post-Incident Review

**What went well:**
- Prometheus local TSDB was intact; Thanos data gap was the only issue
- Recovery was simple once the cardinality source was identified

**What needs improvement:**
- No alert on `prometheus_remote_storage_samples_dropped_total > 0`
- Cardinality increase not caught in pre-deploy metric validation

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add alert: `prometheus_remote_storage_samples_dropped_total` > 0 | Observability | 2026-05-08 | Open |
| Add cardinality gate in CI: reject metrics with user-level labels | Observability | 2026-05-08 | Open |

## Links

- Runbooks: [[RB-015-observability-pipeline-recovery]]
- Related incidents: [[INC-032-prometheus-cardinality-oom]], [[INC-052-datadog-agent-high-cardinality-tags]]
