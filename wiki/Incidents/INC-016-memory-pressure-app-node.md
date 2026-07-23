---
id: INC-016
title: Memory Pressure on App Node — OOM Kill of Multiple Pods
severity: SEV-2
service: api-gateway
environment: prod
category: degradation
date: 2026-03-17
duration: "29m"
detection_gap: "2m"
tags:
  - incident
  - infra
  - memory
  - oom
  - node
  - high
  - prod
  - api
error_family: oom
resolution_runbook: RB-002
resolution_outcome: resolved
---

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
| SLA breach | No — brief degradation, not sustained outage |
| Customer comms | N/A — brief disruption, no status page update |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 20:15 | Kernel OOM killer terminated 4 containers on ip-10-0-3-12 |
| 20:17 | Alert fired: `Node-MemoryPressure` |
| 20:18 | On-call acknowledged (Marcus Webb) |
| 20:22 | OOM kill events confirmed via `dmesg`; node memory at 99.8% |
| 20:25 | Node cordoned; drain initiated to redistribute pods |
| 20:30 | Pods redistributed to other nodes |
| 20:35 | Kubelet eviction threshold updated to 500Mi |
| 20:44 | All services healthy, latency normalized, incident closed |

## Diagnosis

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

1. **Mitigate:** Cordoned and drained the over-packed node to redistribute pods
   ```bash
   kubectl cordon ip-10-0-3-12
   kubectl drain ip-10-0-3-12 --ignore-daemonsets --delete-emptydir-data
   ```

2. **Fix:** Updated kubelet eviction threshold to `500Mi` on all nodes via DaemonSet config
   ```bash
   # kubelet-config.yaml updated:
   # evictionHard:
   #   memory.available: "500Mi"
   ```

3. **Verify:** Confirmed all services healthy and memory requests revised upward
   ```bash
   kubectl get pods --all-namespaces | grep -v Running
   # No unhealthy pods
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Multiple pods OOMKilled on same node | Cordon node, page platform team | #platform-support |
| Cascading failures across services | Escalate to EM + IC | #incident-response |
| Node memory not recovering after kills | Drain and replace node | #platform-support |

## Post-Incident Review

**What went well:**
- Node recovered automatically after OOM kills — no human intervention needed for basic recovery
- Root cause (over-provisioned node) identified quickly via `kubectl describe node`

**What needs improvement:**
- Eviction threshold too conservative — kernel OOM killer should never fire before kubelet acts
- Memory requests significantly underestimated for several services

**Contributing factors (beyond root cause):**
- Total pod memory requests (14.8Gi) + OS overhead (1.2Gi) exceeded 16 GB physical memory
- Kubelet `evictionHard.memory.available` set to `100Mi` — too conservative
- Several pods using 130–160% of their requested memory without hitting limits

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Drain over-packed node, update eviction thresholds | Marcus Webb | 2026-03-17 | Done |
| Increase kubelet `evictionHard.memory.available` to `500Mi` across all nodes | Platform team | 2026-03-31 | Open |
| Run memory profiling on api-gateway and auth-service to set accurate requests | SRE team | 2026-03-31 | Open |
| Add policy: node memory allocatable must not exceed 85% scheduled requests | Platform team | 2026-04-07 | Open |

## Links

- Runbooks: [[RB-002-kubernetes-oom-remediation]], [[RB-007-pod-crash-investigation]]
- Related incidents: [[INC-004-k8s-node-notready]], [[INC-002-k8s-oom-api-pod]]
- PR/commit: N/A
- Post-mortem doc: N/A
