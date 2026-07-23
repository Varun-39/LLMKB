---
id: INC-080
title: Pod Affinity Misconfiguration Blocking Deployment Scheduling
severity: SEV-2
service: reporting-service
environment: prod
category: deployment-failure
date: 2026-04-01
duration: "45m"
tags:
  - incident
  - kubernetes
  - scheduling
  - affinity
  - deployment-failure
  - prod
error_family: pending-pods-resource-pressure
resolution_runbook: RB-022
resolution_outcome: resolved
---

## Summary

A pod affinity rule added during a security hardening sprint required reporting-service pods to co-locate with a `data-tier` labelled pod. That label was never applied to any node, leaving all new reporting-service pods in `Pending` indefinitely and causing a full rollout stall for 45 minutes.

## Symptoms

- `kubectl rollout status deployment/reporting-service` hung indefinitely
- All new pods in `Pending` state with event: `0/6 nodes are available: 6 node(s) didn't match pod affinity rules`
- Old pods still running (rollout paused at 0/3 updated)
- Grafana: reporting-service request latency rising as old pods took full load

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~200 internal analytics users (degraded query performance) |
| Services degraded | reporting-service (no new pods; old pods overloaded) |
| Revenue impact | N/A |
| Duration | 14:10 → 14:55 UTC (45 min) |
| Data loss | None |
| SLA breach | No |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 14:05 | Deployment triggered from CI/CD pipeline |
| 14:10 | New pods enter `Pending` |
| 14:20 | On-call notified by latency alert |
| 14:25 | Deployment paused for investigation |
| 14:40 | Root cause identified: missing node label |
| 14:55 | Affinity rule corrected, rollout completed |

## Diagnosis

1. Checked pending pod events:
   ```bash
   kubectl describe pod reporting-service-new-xxxx -n reporting
   # Events: 0/6 nodes available: 6 node(s) didn't match pod affinity rules
   ```
2. Inspected affinity rule in deployment manifest:
   ```bash
   kubectl get deploy reporting-service -n reporting -o yaml | grep -A 20 affinity
   # requiredDuringSchedulingIgnoredDuringExecution with labelSelector: data-tier
   ```
3. Confirmed no nodes carry the label:
   ```bash
   kubectl get nodes --show-labels | grep data-tier
   # (no output)
   ```

## Resolution

1. **Mitigate:** Paused rollout to prevent further pending pods
   ```bash
   kubectl rollout pause deployment/reporting-service -n reporting
   ```
2. **Fix:** Changed `required` affinity to `preferred` and removed the unsatisfied rule
   ```bash
   kubectl edit deployment reporting-service -n reporting
   # Changed requiredDuringScheduling -> preferredDuringScheduling, weight: 1
   ```
3. **Resume rollout:**
   ```bash
   kubectl rollout resume deployment/reporting-service -n reporting
   ```
4. **Verify:**
   ```bash
   kubectl rollout status deployment/reporting-service -n reporting
   # Successfully rolled out
   ```

## Post-Incident Review

**What went well:**
- Old pods continued serving traffic during the stall — no full outage

**What needs improvement:**
- No pre-deploy validation of scheduling feasibility
- Affinity rules added without testing on cluster topology

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add kube-score / kyverno policy to validate affinity labels exist at deploy time | Platform | 2026-04-15 | Open |
| Add rollout-stall alert (new pods pending > 5 min) | Observability | 2026-04-10 | Open |

## Links

- Runbooks: [[RB-022-autoscaling-hpa-troubleshooting]]
- Related incidents: [[INC-013-k8s-pending-pods-resource-pressure]]
