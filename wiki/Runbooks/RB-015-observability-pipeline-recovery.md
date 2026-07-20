---
id: RB-015
title: Observability Pipeline Recovery (Logs, Metrics, Traces)
service: monitoring
related_services:
  - fluentbit
  - prometheus
  - datadog-agent
  - elasticsearch
severity: SEV-2
environment: prod
category: connectivity
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - observability
  - logging
  - metrics
  - monitoring
  - prod
related_incidents:
  - "[[INC-032-prometheus-cardinality-oom]]"
  - "[[INC-052-datadog-agent-high-cardinality-tags]]"
  - "[[INC-067-fluentbit-backpressure-drop]]"
  - "[[INC-074-network-policy-blocked-prometheus-scrape]]"
related_runbooks:
  - "[[RB-002-kubernetes-oom-remediation]]"
related_guardrails: []
---

## Purpose

Diagnose and recover from observability pipeline failures including log ingestion gaps, metric scraping failures, and trace collection interruptions.

**Desired outcome:** Full observability restored — logs flowing, metrics being scraped, traces collected, dashboards showing data.

## Success Criteria

- Log ingestion rate at baseline on Kibana/Datadog
- Prometheus scrape targets all showing `up`
- No gaps in Grafana dashboards for >5 min
- Fluent Bit/agent pods running without OOM or errors
- Alert pipeline functional (test alert fires and routes correctly)

## Scope

| Attribute | Value |
|-----------|-------|
| Service | monitoring pipeline |
| Related services | fluentbit, prometheus, datadog-agent, elasticsearch |
| Environments | prod, staging |
| Use when | Dashboards showing "No data", log gaps, metric scrape failures |
| Do NOT use when | Application is down (fix the app, not the monitoring) |
| Risk level | Medium |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] Access to monitoring namespace pods
- [ ] Grafana/Kibana access
- [ ] Knowledge of which pipeline component is failing

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Agent/collector pod operations | Cluster admin |
| Grafana | Dashboard and metric verification | Write access |
| Kibana/Datadog | Log ingestion verification | Read access |
| Prometheus UI | Target and rule status | Read access |

## Trigger

- Symptom: Grafana dashboards showing "No data"
- Symptom: Kibana log volume dropped significantly
- Alert: `Prometheus-TargetDown`, `FluentBit-DroppedRecords`
- Symptom: Alerting pipeline not firing (silent failure)

## Triage

1. Identify which pipeline is broken
   ```bash
   # Metrics:
   curl http://prometheus:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health=="down") | .labels.job'
   # Logs:
   kubectl logs -l app=fluent-bit -n logging --tail=20 | grep -i "error\|drop"
   # Agents:
   kubectl get pods -n monitoring | grep -v Running
   ```

2. Determine scope — single service or entire pipeline

3. Check if monitoring pods are healthy
   ```bash
   kubectl get pods -n monitoring
   kubectl get pods -n logging
   ```

## Investigation

1. **Log pipeline — Fluent Bit/Fluentd issues**
   ```bash
   kubectl logs -l app=fluent-bit -n logging --tail=100 | grep -i "error\|retry\|drop\|buffer"
   # What to look for: buffer full, connection refused, dropped records
   ```

2. **Metric pipeline — Prometheus issues**
   ```bash
   kubectl logs -l app=prometheus -n monitoring --tail=50 | grep -i "error\|scrape"
   curl http://prometheus:9090/api/v1/targets | jq '[.data.activeTargets[] | select(.health=="down")] | length'
   ```

3. **Agent issues (Datadog/OTel)**
   ```bash
   kubectl logs -l app=datadog-agent -n monitoring --tail=50 | grep -i "error\|oom\|cardinality"
   kubectl top pods -n monitoring --sort-by=memory
   ```

4. **Decision point:**
   - IF agent OOM → proceed to Mitigation Option A
   - IF destination unreachable → proceed to Mitigation Option B
   - IF NetworkPolicy blocking → proceed to Mitigation Option C
   - IF high cardinality → proceed to Mitigation Option D

## Mitigation

### Option A: Agent OOM — increase memory or fix cardinality

```bash
kubectl set resources daemonset/fluent-bit -n logging --limits=memory=512Mi
kubectl rollout restart daemonset/fluent-bit -n logging
```

### Option B: Destination unreachable (Elasticsearch/Datadog down)

```bash
# Check Elasticsearch:
curl http://elasticsearch:9200/_cluster/health
# If red/unresponsive, restart:
kubectl rollout restart statefulset/elasticsearch -n logging
```

### Option C: NetworkPolicy blocking scrapes

```bash
kubectl get networkpolicy -n <affected-namespace> -o yaml
# Add monitoring namespace to ingress allow list
kubectl patch networkpolicy <policy> -n <namespace> --type='json' \
  -p='[{"op":"add","path":"/spec/ingress/-","value":{"from":[{"namespaceSelector":{"matchLabels":{"name":"monitoring"}}}]}}]'
```

### Option D: High cardinality killing agents

```bash
# Identify high-cardinality metric:
curl http://prometheus:9090/api/v1/label/__name__/values | jq '.data | length'
# Drop problematic metric at source or add relabeling rule
```

**After mitigation:** Verify data flowing in Grafana/Kibana within 5 minutes.

## Verification

- [ ] Log ingestion rate at baseline
- [ ] All Prometheus targets `up`
- [ ] Grafana dashboards showing current data
- [ ] Agent pods running stably
- [ ] Test alert fires correctly

```bash
kubectl get pods -n monitoring -n logging | grep -v Running
# Expected: empty (all running)
curl http://prometheus:9090/api/v1/targets | jq '[.data.activeTargets[] | select(.health=="down")] | length'
# Expected: 0
```

## Failure Signals

- Agents keep crashing after memory increase
- Destination still unreachable
- Data still not appearing in dashboards
- Alert pipeline still silent

**If any failure signal is present:** Escalate.

## Rollback

1. **Undo memory changes:** Revert daemonset resources
2. **Undo NetworkPolicy changes:** Remove added ingress rule
3. **If Elasticsearch corrupted:** Restore from snapshot

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Complete observability gap >30 min | Platform team + EM | #incident-response | 10 min |
| Elasticsearch cluster red | Data platform team | #data-eng | 10 min |
| Cannot fix within 20 min | Senior SRE | PagerDuty | 5 min |

## Notes

- **Observability gaps are security risks** — you can't detect breaches without logs.
- **Fluent Bit filesystem buffering** prevents log loss during destination slowdowns.
- **Prometheus cardinality explosion** is the #1 cause of monitoring OOM. See [[INC-032-prometheus-cardinality-oom]].
- **NetworkPolicy changes must always account for monitoring namespace.** See [[INC-074-network-policy-blocked-prometheus-scrape]].

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Block Fluent Bit output in staging, verify alerting fires and recovery procedure works.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
