---
id: RB-022
title: Autoscaling (HPA) Troubleshooting and Stabilization
service: "*"
related_services:
  - search-api
  - api-gateway
  - metrics-server
severity: SEV-2
environment: prod
category: performance
risk_level: medium
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - kubernetes
  - hpa
  - autoscaling
  - performance
  - prod
related_incidents:
  - "[[INC-049-hpa-flapping-cpu-memory-mismatch]]"
  - "[[INC-013-k8s-pending-pods-resource-pressure]]"
related_runbooks:
  - "[[RB-004-high-cpu-usage]]"
related_guardrails: []
---

## Purpose

Diagnose and fix HPA (Horizontal Pod Autoscaler) issues including flapping, failure to scale, wrong metrics, and stabilization window problems.

**Desired outcome:** HPA scaling smoothly based on appropriate metrics, no oscillation, replicas matching load demand.

## Success Criteria

- HPA replica count stable (not changing more than once per 5 minutes during steady state)
- Target metric utilization within 10% of target value
- No request drops during scale-down
- metrics-server providing accurate data
- No Pending pods due to resource constraints

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any service with HPA configured |
| Related services | search-api, api-gateway, metrics-server |
| Environments | prod, staging |
| Use when | HPA flapping, not scaling when expected, or scaling too aggressively |
| Do NOT use when | Load is legitimately variable and HPA is responding correctly |
| Risk level | Medium |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to affected namespace
- [ ] Metrics-server running and healthy
- [ ] Grafana access to service metrics

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | HPA and deployment inspection | Cluster admin |
| Grafana | Metric trends | Read access |
| metrics-server | Pod resource metrics | Cluster component |

## Trigger

- HPA replica count oscillating rapidly (3+ changes in 10 min)
- Service degraded but HPA not scaling up
- Pods entering Pending (HPA scaled beyond cluster capacity)
- Alert: `HPA-ReplicaFlapping`, `*-HighLatency` despite HPA configured

## Triage

1. Check HPA current state
   ```bash
   kubectl get hpa <name> -n <namespace>
   # What to look for: TARGETS (current/target), MINPODS, MAXPODS, REPLICAS
   ```

2. Check HPA events
   ```bash
   kubectl describe hpa <name> -n <namespace>
   # What to look for: ScalingActive conditions, unable to fetch metrics, recommendations
   ```

3. Check metrics-server health
   ```bash
   kubectl top pods -n <namespace> -l app=<service>
   # If error → metrics-server is down
   ```

## Investigation

1. **Is HPA getting valid metrics?**
   ```bash
   kubectl get hpa <name> -n <namespace> -o yaml | grep -A10 "currentMetrics"
   # What to look for: <unknown> = metrics not available
   ```

2. **Is the target metric appropriate?**
   ```bash
   kubectl top pods -n <namespace> -l app=<service>
   # Compare actual resource usage to HPA target percentage
   ```

3. **Check for scale-down flapping**
   ```bash
   kubectl get events -n <namespace> --sort-by='.lastTimestamp' | grep -i "SuccessfulRescale" | tail -20
   # What to look for: rapid scale up/down oscillation
   ```

4. **Decision point:**
   - IF metrics unavailable → proceed to Mitigation Option A
   - IF flapping → proceed to Mitigation Option B
   - IF not scaling when needed → proceed to Mitigation Option C
   - IF scaling beyond capacity → proceed to Mitigation Option D

## Mitigation

### Option A: Fix metrics (metrics-server down)

```bash
kubectl rollout restart deployment/metrics-server -n kube-system
kubectl rollout status deployment/metrics-server -n kube-system
```

### Option B: Stop flapping — add stabilization window

```bash
kubectl patch hpa <name> -n <namespace> --type='merge' -p='{
  "spec": {
    "behavior": {
      "scaleDown": {
        "stabilizationWindowSeconds": 300,
        "policies": [{"type": "Percent", "value": 10, "periodSeconds": 60}]
      }
    }
  }
}'
```

### Option C: Fix scale-up (wrong metric or target too high)

```bash
kubectl patch hpa <name> -n <namespace> --type='merge' -p='{
  "spec": {
    "metrics": [{
      "type": "Resource",
      "resource": {"name": "cpu", "target": {"type": "Utilization", "averageUtilization": 60}}
    }]
  }
}'
```

### Option D: Cap max replicas to cluster capacity

```bash
kubectl patch hpa <name> -n <namespace> --type='merge' -p='{"spec":{"maxReplicas":<safe-max>}}'
```

**After mitigation:** Monitor — HPA should stabilize within 5 minutes.

## Verification

- [ ] HPA showing valid current metrics
- [ ] Replica count stable
- [ ] No rapid scaling events
- [ ] Service latency at baseline
- [ ] No Pending pods

```bash
kubectl get hpa <name> -n <namespace> -w
# Watch for 5 min — replicas should be stable
```

## Failure Signals

- HPA still flapping despite stabilization window
- Metrics-server not recovering
- Service degraded but HPA at maxReplicas
- Pods Pending (cluster capacity reached)

**If any failure signal is present:** Consider manual replica override while investigating.

## Rollback

1. **Override HPA with manual scaling:**
   ```bash
   kubectl scale deployment/<name> -n <namespace> --replicas=<safe-number>
   kubectl patch hpa <name> -n <namespace> -p '{"spec":{"minReplicas":<safe>,"maxReplicas":<safe>}}'
   ```

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| HPA causing production degradation | Service owner + SRE | #incident-response | 10 min |
| Cluster capacity exceeded | Platform team | #platform-support | 15 min |
| metrics-server won't recover | Platform team | #platform-support | 10 min |

## Notes

- **CPU is a poor scaling metric for I/O-bound workloads.** Use custom metrics (RPS, queue depth) instead.
- **Default stabilization window is 5 min for scale-down, 0 for scale-up.** This often isn't enough for bursty workloads.
- **HPA cannot exceed node capacity.** If maxReplicas requires more resources than available nodes, pods will Pending.
- See [[INC-049-hpa-flapping-cpu-memory-mismatch]] for a real-world flapping example.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Generate load against staging service, verify HPA scales up and stabilizes.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
