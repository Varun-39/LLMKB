---
id: INC-094
title: Node Affinity Zone Imbalance Caused AZ Failure Impact to be Catastrophic
severity: SEV-1
service: api-gateway
environment: prod
category: outage
date: 2026-04-29
duration: "22m"
tags:
  - incident
  - kubernetes
  - availability-zone
  - node-affinity
  - multi-az
  - api-gateway
  - prod
---

## Summary

All 6 api-gateway pods were scheduled onto nodes in us-east-1a due to a node affinity preference (weight: 100) favouring that zone — intended as a soft preference but effectively acting as hard pinning due to resource availability. An AWS AZ outage in us-east-1a took down all 6 pods simultaneously, causing a full api-gateway outage despite the cluster spanning 3 AZs.

## Symptoms

- AWS health dashboard: us-east-1a degraded (network connectivity issues)
- All 6 api-gateway pods on nodes in us-east-1a — all unreachable simultaneously
- Load balancer health checks: all targets unhealthy
- 100% of API traffic returning 503
- SEV-1 fired within 90 seconds

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All active users (~18,000) |
| Services degraded | api-gateway (full outage), all downstream services |
| Revenue impact | ~$67K |
| Duration | 03:12 → 03:34 UTC (22 min) |
| Data loss | None |
| SLA breach | Yes — critical availability SLA breached |
| Customer comms | Status page updated at 03:14 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 03:10 | AWS us-east-1a network degradation begins |
| 03:12 | All api-gateway pods unreachable |
| 03:13 | SEV-1 PagerDuty alert |
| 03:15 | On-call acknowledged |
| 03:20 | Pods manually rescheduled to us-east-1b and us-east-1c |
| 03:34 | Service fully recovered |

## Diagnosis

1. Confirmed all pods in one AZ:
   ```bash
   kubectl get pods -n api -o wide | awk '{print $7}' | sort | uniq -c
   # 6 ip-10-0-1-xx.us-east-1a.compute.internal
   ```
2. Checked node affinity:
   ```bash
   kubectl get deploy api-gateway -n api -o yaml | grep -A20 affinity
   # preferredDuringScheduling weight: 100 for us-east-1a
   # (no hard anti-affinity to spread across zones)
   ```
3. Confirmed no pod anti-affinity rule existed:
   ```bash
   kubectl get deploy api-gateway -n api -o yaml | grep podAntiAffinity
   # (no output)
   ```

## Resolution

1. **Immediate:** Deleted pods from us-east-1a — Kubernetes rescheduled to remaining zones
   ```bash
   kubectl delete pods -n api -l app=api-gateway --field-selector spec.nodeName=worker-1a-node01
   kubectl delete pods -n api -l app=api-gateway --field-selector spec.nodeName=worker-1a-node02
   ```
2. **Fix:** Added `podAntiAffinity` to spread pods across AZs:
   ```yaml
   podAntiAffinity:
     requiredDuringSchedulingIgnoredDuringExecution:
     - labelSelector:
         matchLabels:
           app: api-gateway
       topologyKey: topology.kubernetes.io/zone
   ```
3. Verified pods distributed across 3 AZs (2 per zone)

## Post-Incident Review

**What went well:**
- Recovery was fast once the cause was identified — deleting pods triggered rescheduling

**What needs improvement:**
- Zone preference with weight 100 is near-equivalent to hard pinning when capacity allows it
- No zone distribution check in deployment validation

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add pod anti-affinity (topology: zone) to all stateless production deployments | Platform | 2026-05-06 | Open |
| Add topology spread constraints to deployment helm chart defaults | Platform | 2026-05-06 | Open |
| Add zone distribution check to deployment admission webhook | Platform | 2026-05-13 | Open |

## Links

- Runbooks: [[RB-019-kubernetes-node-notready]]
- Related incidents: [[INC-004-k8s-node-notready]], [[INC-054-zombie-pods-node-network-partition]]
