---
id: INC-016
title: Memory Pressure on App Node — OOM Kill of Multiple Pods
severity: SEV-2
service: api-gateway
environment: prod
category: degradation
status: resolved
owner: Marcus Webb
assigned-to: Marcus Webb
date: 2026-03-17
duration: 29 minutes
created: 2026-03-17
updated: 2026-03-17
tags:
  - incident
  - infra
  - memory
  - oom
  - node
  - high
  - prod
  - api
related_runbooks:
  - "[[RB-001-kubernetes-oom]]"
  - "[[RB-006-pod-crash]]"
related_incidents:
  - "[[INC-004-k8s-node-notready]]"
  - "[[INC-002-k8s-oom-api-pod]]"
---

# INC-016 — Memory Pressure on App Node: OOM Kill of Multiple Pods

## Summary

At 20:15 UTC on 2026-03-17, the Linux kernel OOM killer on `ip-10-0-3-12` terminated 4 containers across 3 different services as node memory hit 99.8% utilization. No individual pod had exceeded its memory limit, but the sum of all pod requests plus OS overhead exceeded the node's physical 16 GB. Kubernetes did not trigger eviction proactively because eviction thresholds were set too conservatively. The node recovered after the OOM kills reduced memory pressure, but affected pods had elevated restart counts.

## Symptoms

- PagerDuty: `Node-MemoryPressure` at 20:17 UTC (threshold: 95% for 3 min)
- `dmesg` on node: `Out of memory: Kill process <pid> (java)` × 4 entries at 20:15 UTC
- Affected pods: `api-gateway-xxx`, `auth-service-yyy`, `notifications-svc-zzz` all OOMKilled
- Kubernetes events: `OOMKilling` reason for each pod
- API error rate spiked to 11% for 8 minutes while pods restarted
- Node `free -h`: 78 MB free out of 16 GB before kill events

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~4,100 concurrent users across affected services |
| Services degraded | api-gateway, auth-service, notifications-service (all pods restarting) |
| Revenue impact | ~$9K from failed requests during restart window |
| Duration | 20:15 → 20:44 UTC (29 min) |
| Data loss | None |

## Possible Causes

1. **Memory request sum exceeded node capacity** — total pod memory requests = 14.8 GB; with OS overhead (1.2 GB), physical memory exhausted
2. **Overly conservative eviction thresholds** — kubelet `evictionHard.memory.available` set to `100Mi`, not triggered at 78 MB before kernel OOM
3. **Memory usage spiked above requests** — several pods using 120–150% of their requested memory (requests too low relative to actual usage)
4. **Burst workload** — evening cron jobs on reporting-service added ~800 MB short-lived memory pressure that tipped balance

## Troubleshooting Steps

1. Confirmed OOM kill events on node
   ```bash
   ssh ec2-user@10.0.3.12
   dmesg | grep "Out of memory" | tail -10
   # [1234567.89] Out of memory: Kill process 29341 (java) score 892
   # (4 such entries between 20:15:02 and 20:15:07 UTC)
   ```

2. Reviewed node memory state at time of incident (from Grafana time-series)
   - Node memory hit 99.8% at 20:14:55 UTC
   - Kubelet eviction threshold was `100Mi` — never triggered (dipped below only momentarily)

3. Checked pod memory usage vs. requests
   ```bash
   kubectl top pods --all-namespaces --sort-by=memory | head -20
   kubectl get pods --all-namespaces -o json \
     | jq '.items[] | .spec.containers[].resources.requests.memory'
   # Multiple pods using 130–160% of requested memory
   ```

4. Calculated total requested memory on node
   ```bash
   kubectl describe node ip-10-0-3-12 | grep -A3 "Allocated resources"
   # memory requests: 14.8Gi / 15.2Gi allocatable (97%)
   ```

5. Checked kubelet eviction config
   ```bash
   cat /etc/kubernetes/kubelet-config.yaml | grep eviction
   # evictionHard:
   #   memory.available: "100Mi"   ← should be ~500Mi or 5% of node memory
   ```

## Resolution

1. Node recovered naturally after OOM kills reduced memory pressure (no manual action needed)
2. Identified over-packed node — redistributed pods via temporary cordon + drain
   ```bash
   kubectl cordon ip-10-0-3-12
   kubectl drain ip-10-0-3-12 --ignore-daemonsets --delete-emptydir-data
   ```

3. Updated kubelet eviction threshold to `500Mi` on all nodes via DaemonSet config

4. Revised memory requests upward for api-gateway and auth-service to match observed P95 usage

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Multiple pods OOMKilled on same node | Cordon node, page platform team | #platform-support |
| Cascading failures across services | Escalate to EM + IC | #incident-response |
| Node memory not recovering after kills | Drain and replace node | #platform-support |

## Post-Incident Notes

**Went well:**
- Node recovered automatically after OOM kills — no human intervention needed for basic recovery
- Root cause (over-provisioned node) identified quickly via `kubectl describe node`

**Improve:**
- Eviction threshold too conservative — kernel OOM killer should never fire before kubelet acts
- Memory requests significantly underestimated for several services

**Action items:**
- [x] Drained over-packed node, updated eviction thresholds
- [ ] Increase kubelet `evictionHard.memory.available` to `500Mi` across all nodes
- [ ] Run memory profiling on api-gateway and auth-service to set accurate requests
- [ ] Add policy: node memory allocatable must not exceed 85% scheduled requests

## Related Runbooks

- [[RB-001-kubernetes-oom]]
- [[RB-006-pod-crash]]
