---
id: INC-052
title: Datadog Agent Memory Spike from High-Cardinality Custom Tags
severity: SEV-3
service: monitoring
environment: prod
category: capacity
date: 2026-05-10
duration: "30m"
tags:
  - incident
  - datadog
  - monitoring
  - cardinality
  - memory
  - moderate
  - prod
---

## Summary

A developer added a custom metric tag `user_id` to the payment-service Datadog integration, creating millions of unique time series. The Datadog agent on 4 nodes hit 2GB memory usage (limit: 1GB), OOMKilling the agent and creating a 30-minute observability gap. Metrics, logs, and APM traces stopped being collected from those nodes.

## Symptoms

- Datadog dashboard: gaps in metrics from 4 nodes
- Datadog agent pods: OOMKilled
- `datadog-agent` memory: 2GB+ before crash
- Custom metrics count in Datadog: jumped from 15,000 to 2.4 million

## Diagnosis

1. Agent OOMKilled
   ```bash
   kubectl describe pod datadog-agent-xyz -n monitoring | grep -A3 "Last State"
   # Reason: OOMKilled
   ```

2. High cardinality metric identified
   ```bash
   kubectl logs datadog-agent-xyz -n monitoring --previous | grep "Too many custom metrics"
   # WARNING: custom metric payment.transaction.amount has 2.4M unique tag combinations
   ```

3. Tag `user_id` found in payment-service StatsD config (committed 2 hours ago)

## Resolution

1. **Mitigate:** Removed `user_id` tag from StatsD configuration
   ```bash
   kubectl set env deployment/payment-service -n payments STATSD_TAGS="service:payment,env:prod"
   kubectl rollout restart deployment/payment-service -n payments
   ```

2. **Fix:** Restarted Datadog agents
   ```bash
   kubectl rollout restart daemonset/datadog-agent -n monitoring
   ```

3. **Verify:** Agent memory stable at 200MB, metrics flowing

## Post-Incident Review

- No guardrail preventing high-cardinality tags in StatsD config
- Added CI check: reject metric tags with known high-cardinality fields (user_id, request_id, etc.)
- Added Datadog agent alert: memory >60% of limit for 5 minutes
- Added custom metrics count alert: >50,000 unique series per service

## Links

- Runbooks: [[RB-015-observability-pipeline-recovery]]
- Related incidents: [[INC-032-prometheus-cardinality-oom]]
