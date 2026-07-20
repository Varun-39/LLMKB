---
id: RB-033
title: Alert Routing Validation and False Positive Tuning
service: monitoring
related_services:
  - pagerduty
  - prometheus
  - grafana
severity: SEV-3
environment: prod
category: performance
risk_level: low
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - alerting
  - pagerduty
  - prometheus
  - false-positive
  - monitoring
  - prod
related_incidents:
  - "[[INC-074-network-policy-blocked-prometheus-scrape]]"
  - "[[INC-032-prometheus-cardinality-oom]]"
related_runbooks:
  - "[[RB-015-observability-pipeline-recovery]]"
related_guardrails: []
---

## Purpose

Validate alert routing, tune noisy alerts, and fix false positives/negatives in the alerting pipeline to maintain signal-to-noise ratio.

**Desired outcome:** Alerts routing to correct team, actionable signal maintained, false positive rate <5%.

## Success Criteria

- Test alert routes to correct PagerDuty service and escalation policy
- No recurring false positive alerts (>3 false pages in a week = needs tuning)
- Critical alerts not suppressed or lost
- All alerting rules evaluating successfully in Prometheus

## Scope

| Attribute | Value |
|-----------|-------|
| Service | monitoring/alerting pipeline |
| Related services | pagerduty, prometheus, grafana |
| Environments | prod |
| Use when | Alert not firing when expected, routing to wrong team, excessive false positives |
| Do NOT use when | Underlying service issue causing alert to fire (fix the service) |
| Risk level | Low |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] Prometheus/Alertmanager access
- [ ] PagerDuty admin access
- [ ] Knowledge of which alert is misbehaving

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| Prometheus UI | Alert rule inspection | Admin |
| Alertmanager UI | Routing and silencing | Admin |
| PagerDuty | Service and escalation policy | Admin |
| `amtool` | Alertmanager CLI testing | Local |

## Trigger

- Alert not firing when service is degraded (false negative)
- Alert firing when service is healthy (false positive)
- Alert routing to wrong team
- Excessive paging causing alert fatigue

## Triage

1. Check if alert is actually evaluating
   ```bash
   curl http://prometheus:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.name=="<alert-name>")'
   # What to look for: state (firing/pending/inactive), lastEvaluation
   ```

2. Check Alertmanager routing
   ```bash
   amtool config routes --config.file=/etc/alertmanager/alertmanager.yml test <alert-labels>
   # What to look for: which receiver matches
   ```

3. Check if alert is silenced
   ```bash
   amtool silence query --alertmanager.url=http://alertmanager:9093
   ```

## Mitigation

### Fix false positive (alert too sensitive):

```bash
# Edit Prometheus rule to adjust threshold or add for duration:
kubectl edit configmap prometheus-rules -n monitoring
# Example: change "for: 1m" to "for: 5m" or adjust threshold
# Reload Prometheus:
curl -X POST http://prometheus:9090/-/reload
```

### Fix routing (going to wrong team):

```bash
# Edit Alertmanager config:
kubectl edit configmap alertmanager-config -n monitoring
# Update route matching labels → correct receiver
# Reload Alertmanager:
curl -X POST http://alertmanager:9093/-/reload
```

### Fix false negative (alert not firing):

```bash
# Check if metric exists:
curl "http://prometheus:9090/api/v1/query?query=<metric-name>"
# If metric missing → fix scraping (see [[RB-015-observability-pipeline-recovery]])
# If metric present → fix alert expression threshold
```

## Verification

- [ ] Test alert fires when condition is met
- [ ] Alert routes to correct PagerDuty service
- [ ] No active silences suppressing critical alerts
- [ ] False positive rate acceptable (<5%)

```bash
# Send test alert:
amtool alert add test-alert severity=critical service=test --alertmanager.url=http://alertmanager:9093
# Verify it appears in PagerDuty, then resolve:
amtool alert add test-alert severity=critical service=test --end=$(date -u +"%Y-%m-%dT%H:%M:%SZ" -d "+1 min")
```

## Notes

- **Alert fatigue kills on-call.** If a team gets >5 false pages per week, the alert must be tuned or suppressed.
- **for duration** is your friend — prevents transient spikes from paging.
- **Test alerts after every routing change** — a misconfigured route can silently drop critical alerts.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Monthly
- **Next review:** 2026-07-15
- **Test method:** Fire test alert via amtool, verify routing end-to-end.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
