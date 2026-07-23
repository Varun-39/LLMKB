---
id: INC-074
title: NetworkPolicy Blocked Prometheus Scraping — 4-Hour Metrics Gap
severity: SEV-3
service: monitoring
environment: prod
category: configuration
date: 2026-06-23
duration: "4h"
tags:
  - incident
  - network-policy
  - prometheus
  - monitoring
  - kubernetes
  - moderate
  - prod
error_family: unknown
resolution_runbook: RB-015
resolution_outcome: resolved
---

## Summary

A new NetworkPolicy applied to the `payments` namespace for security hardening blocked all ingress traffic except from the `api` namespace. Prometheus (running in `monitoring` namespace) could no longer scrape payment-service metrics. The issue went undetected for 4 hours because Prometheus does not alert on individual scrape targets going stale by default.

## Symptoms

- No alerts fired (Prometheus silently stopped scraping)
- Grafana: payment-service dashboards showed "No data" after 4 hours
- Prometheus targets page: payment-service endpoints showing `context deadline exceeded`
- Discovered during routine dashboard review

## Diagnosis

1. Confirmed scrape failure
   ```bash
   curl http://prometheus:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="payment-service") | .health'
   # "down" — last successful scrape 4h ago
   ```

2. NetworkPolicy blocking Prometheus
   ```bash
   kubectl get networkpolicy -n payments -o yaml
   # Only allows ingress from namespace: api
   # Prometheus in namespace: monitoring — blocked
   ```

## Resolution

1. **Fix:** Added Prometheus namespace to NetworkPolicy ingress allow list
   ```bash
   kubectl patch networkpolicy payment-restrict -n payments --type='json' \
     -p='[{"op":"add","path":"/spec/ingress/-","value":{"from":[{"namespaceSelector":{"matchLabels":{"name":"monitoring"}}}],"ports":[{"port":8080,"protocol":"TCP"}]}}]'
   ```

2. **Verify:** Prometheus targets healthy again
   ```bash
   curl http://prometheus:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="payment-service") | .health'
   # "up"
   ```

## Post-Incident Review

- NetworkPolicy changes must account for monitoring ingress
- Added Prometheus scrape target health alert: if any target is down for >10 minutes
- Created NetworkPolicy template that always includes monitoring namespace
- Added CI check: new NetworkPolicies must allow monitoring namespace on metrics port

## Links

- Runbooks: [[RB-015-observability-pipeline-recovery]]
- Related incidents: [[INC-032-prometheus-cardinality-oom]]
