---
id: INC-004
title: K8s Node NotReady — Kubelet Unresponsive
severity: SEV-2
service: api-gateway
environment: prod
category: outage
status: resolved
owner: Marcus Webb
assigned-to: Marcus Webb
date: 2026-05-18
duration: 52 minutes
created: 2026-05-18
updated: 2026-05-18
tags:
  - incident
  - kubernetes
  - node
  - kubelet
  - high
  - prod
  - api
related_runbooks:
  - "[[RB-006-pod-crash]]"
related_incidents: []
---

# INC-004 — K8s Node NotReady: Kubelet Unresponsive

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

## Possible Causes

1. **Kubelet OOM-killed** — kubelet process terminated by kernel OOM killer due to node memory pressure
2. **Disk pressure** — `/var/lib/kubelet` filled by container logs causing kubelet to hang
3. **Network partition** — transient split between node and control plane causing false NotReady
4. **Kernel bug** — known panic on specific AMI version under high iowait

## Troubleshooting Steps

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

1. Cordoned node to prevent new scheduling
   ```bash
   kubectl cordon ip-10-0-1-47
   ```

2. Deleted unbounded reporting-service pod to free memory
   ```bash
   kubectl delete pod reporting-svc-64f7d-pp91 -n reporting
   ```

3. Restarted kubelet
   ```bash
   systemctl restart kubelet
   sleep 30 && systemctl status kubelet
   # Active: running
   ```

4. Uncordoned node once healthy
   ```bash
   kubectl uncordon ip-10-0-1-47
   kubectl get nodes  # ip-10-0-1-47 Ready
   ```

5. Confirmed pending pods scheduled
   ```bash
   kubectl get pods -n gateway -l app=api-gateway
   # All 5 Running
   ```

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Node unrecoverable after 20 min | Terminate and replace via ASG | #platform-support |
| >2 nodes NotReady simultaneously | Declare SEV-1, page EM + IC | #incident-response |
| Pods cannot reschedule due to capacity | Engage platform team for scaling | #platform-support |

## Post-Incident Notes

**Went well:**
- Kubernetes eviction and rescheduling handled most pods automatically
- Node SSH access available, enabling fast kubelet restart

**Improve:**
- reporting-service pods had no resource limits — unbounded memory use went undetected
- No node memory pressure alert below NodeNotReady threshold

**Action items:**
- [x] Restarted kubelet, restored node
- [ ] Set memory limits on all reporting-service pods
- [ ] Add Grafana alert: node memory >85%
- [ ] Audit all pods in cluster with no resource limits

## Related Runbooks

- [[RB-006-pod-crash]]
