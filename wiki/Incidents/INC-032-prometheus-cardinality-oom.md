---
id: INC-032
title: Prometheus OOM Due to High Cardinality Metric Explosion
severity: SEV-2
service: monitoring
environment: prod
category: capacity
date: 2026-03-25
duration: "1h05m"
tags:
  - incident
  - prometheus
  - monitoring
  - cardinality
  - oom
  - metrics
error_family: oom
resolution_runbook: RB-015
resolution_outcome: resolved
---

## Summary

Prometheus server OOMKilled after a new service deployed metrics with unbounded label cardinality (`user_id` as a label). Time series count jumped from 1.2M to 18M in 2 hours. Prometheus consumed all 16GB RAM and was killed, causing a 65-minute monitoring blackout.

## Symptoms

- PagerDuty: `Prometheus-Down` at 11:45 UTC
- Grafana dashboards showing "No data" across all panels
- Prometheus pod: OOMKilled, `Exit Code: 137`
- `promtool tsdb analyze` showed 18M active series (normal: 1.2M)
- Alertmanager stopped receiving alerts — all alerting silenced

## Diagnosis

1. Checked TSDB stats before crash (from WAL replay logs):
   ```
   msg="TSDB compaction" series=18234521
   ```
2. Identified the source:
   ```promql
   topk(10, count by (__name__)({__name__=~".+"}))
   # http_request_duration_bucket{user_id="..."} → 16.8M series
   ```
3. New `analytics-service` deployed with metric labels including `user_id` (500K unique users × 30+ endpoints × histogram buckets = explosion)
4. No cardinality limit or relabeling rule in Prometheus config

## Resolution

1. Added emergency relabeling to drop the metric before scrape:
   ```yaml
   # prometheus.yml
   metric_relabel_configs:
     - source_labels: [__name__]
       regex: 'http_request_duration_bucket'
       target_label: user_id
       action: labeldrop
   ```
2. Increased Prometheus memory limit temporarily to 24GB for WAL recovery
3. Restarted Prometheus
4. Coordinated with analytics team to remove `user_id` label from their metrics endpoint
5. Series count returned to 1.4M after 2 scrape intervals

## Post-Incident Review

- No pre-deploy check existed for metric cardinality impact
- Added `prom-label-enforcer` admission controller: rejects scrape configs with high-cardinality labels
- Added alert: `prometheus_tsdb_head_series > 5000000`
- Established policy: labels must have cardinality < 1000 per metric

## Links

- Related: [[RB-015-observability-pipeline-recovery]]
