---
id: INC-004
title: K8s Node NotReady — Kubelet Unresponsive
severity: SEV-2
service: api-gateway
environment: prod
category: outage
date: 2026-05-18
duration: "52m"
detection_gap: "2m"
tags:
  - incident
  - kubernetes
  - node
  - kubelet
  - high
  - prod
  - api
---

## Summary

Production node `ip-10-0-1-47` entered NotReady state at 22:11 UTC on 2026-05-18 after the kubelet process became unresponsive. Seven pods across api-gateway and notifications-service were evicted and rescheduled to remaining nodes. Two pods failed to reschedule due to insufficient capacity, causing partial API degradation for 52 minutes until the node was recovered and capacity restored.

## Symptoms

- PagerDuty: `K8s-NodeNotReady` at 22:13 UTC
- `kubectl get nodes` showed `ip-10-0-1-47` in `NotReady` state
- 2 api-gateway pods stuck in `Pending` (insufficient CPU on remaining nodes)
- P95 API latency increased from 210 ms to 1.8 s
- notifications-service: ~400 queued events not delivered (held in queue, not lost)

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~3,000 users on affected API endpoints |
| Services degraded | api-gateway (2 of 5 pods missing), notifications-service (delayed delivery) |
| Revenue impact | Minimal — degraded performance, not fully down |
| Duration | 22:11 → 23:03 UTC (52 min) |
| Data loss | None — notifications replayed from queue post-recovery |
| SLA breach | No — degradation stayed within SLA threshold |
| Customer comms | N/A — partial degradation, no status page update |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 22:11 | Kubelet stopped responding; node entered NotReady |
| 22:13 | Alert fired: `K8s-NodeNotReady` |
| 22:14 | On-call acknowledged (Marcus Webb) |
| 22:20 | SSH to node; kubelet found in failed state |
| 22:25 | Root cause identified — kubelet OOM-killed by kernel |
| 22:30 | Unbounded reporting-service pod killed to free memory |
| 22:32 | Kubelet restarted successfully |
| 22:35 | Node uncordoned; pending pods scheduled |
| 23:03 | All pods healthy, latency normalized, incident closed |

## Diagnosis

1. Confirmed node state and conditions
   ```bash
   kubectl get nodes -o wide
   kubectl describe node ip-10-0-1-47 | grep -A10 "Conditions"
   # KubeletNotReady: kubelet stopped posting node status
   ```

2. SSH to the affected node
   ```bash
   ssh ec2-user@10.0.1.47
   ```

3. Checked kubelet process status
   ```bash
   systemctl status kubelet
   # Active: failed (Result: exit-code) since 22:11:03 UTC
   ```

4. Reviewed kubelet journal for root cause
   ```bash
   journalctl -u kubelet --since "22:00" --until "22:15" | tail -50
   # OOM kill signal received — kubelet process terminated by kernel
   ```

5. Verified node resource state
   ```bash
   free -h
   # Mem: 15.4G total, 15.1G used (98%)
   df -h /var/lib/kubelet
   # 94% used
   ```

6. Identified memory hog: `reporting-service` pod consuming 11Gi with no resource limits

## Resolution

1. **Mitigate:** Cordoned node and deleted unbounded reporting-service pod to free memory
   ```bash
   kubectl cordon ip-10-0-1-47
   kubectl delete pod reporting-svc-64f7d-pp91 -n reporting
   ```

2. **Fix:** Restarted kubelet and uncordoned node
   ```bash
   systemctl restart kubelet
   sleep 30 && systemctl status kubelet
   # Active: running
   kubectl uncordon ip-10-0-1-47
   kubectl get nodes  # ip-10-0-1-47 Ready
   ```

3. **Verify:** Confirmed pending pods scheduled and service healthy
   ```bash
   kubectl get pods -n gateway -l app=api-gateway
   # All 5 Running
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Node unrecoverable after 20 min | Terminate and replace via ASG | #platform-support |
| >2 nodes NotReady simultaneously | Declare SEV-1, page EM + IC | #incident-response |
| Pods cannot reschedule due to capacity | Engage platform team for scaling | #platform-support |

## Post-Incident Review

**What went well:**
- Kubernetes eviction and rescheduling handled most pods automatically
- Node SSH access available, enabling fast kubelet restart

**What needs improvement:**
- reporting-service pods had no resource limits — unbounded memory use went undetected
- No node memory pressure alert below NodeNotReady threshold

**Contributing factors (beyond root cause):**
- reporting-service pod consuming 11Gi with no memory limit set
- Node had insufficient headroom for workload spikes
- No pod resource limit enforcement policy across the cluster

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Restart kubelet, restore node | Marcus Webb | 2026-05-18 | Done |
| Set memory limits on all reporting-service pods | James Okafor | 2026-06-01 | Open |
| Add Grafana alert: node memory >85% | SRE team | 2026-06-01 | Open |
| Audit all pods in cluster with no resource limits | Platform team | 2026-06-08 | Open |

## Links

- Runbooks: [[RB-007-pod-crash-investigation]]
- Related incidents: [[INC-013-k8s-pending-pods-resource-pressure]]
- PR/commit: N/A
- Post-mortem doc: N/A
