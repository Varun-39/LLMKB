---
id: INC-013
title: Pods Stuck Pending — Cluster CPU Capacity Exhausted
severity: SEV-2
service: payment-service
environment: prod
category: degradation
status: resolved
owner: Priya Sharma
assigned-to: Priya Sharma
date: 2026-04-03
duration: 44 minutes
created: 2026-04-03
updated: 2026-04-03
tags:
  - incident
  - kubernetes
  - scheduling
  - cpu
  - capacity
  - high
  - prod
  - payments
related_runbooks:
  - "[[RB-006-pod-crash]]"
  - "[[RB-003-high-cpu]]"
related_incidents:
  - "[[INC-004-k8s-node-notready]]"
  - "[[INC-007-high-cpu-payment-service]]"
---

# INC-013 — Pods Stuck Pending: Cluster CPU Capacity Exhausted

## Summary

A HPA-triggered scale-out of payment-service at 15:30 UTC on 2026-04-03 left 6 new pods in `Pending` state because all cluster nodes had insufficient allocatable CPU. The scheduler could not place the pods due to CPU requests set too high combined with a reporting-service batch job that had claimed 40% of cluster CPU without limits. Payments processed slowly on under-provisioned pods for 44 minutes until the batch job completed and pods were scheduled.

## Symptoms

- PagerDuty: `PaymentService-HighLatency` at 15:33 UTC
- `kubectl get pods -n payments` showed 6 pods in `Pending` for >10 min
- Kubernetes scheduler events: `0/6 nodes are available: insufficient cpu`
- P95 latency on `/payments/initiate`: 340 ms → 2.1 s
- HPA showed `desired: 10, ready: 4` for payment-service
- Grafana: cluster CPU allocatable at 98%

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~6,200 users during peak payment window |
| Services degraded | payment-service (under-replicated, high latency) |
| Revenue impact | ~$18K in degraded/timed-out checkout completions |
| Duration | 15:30 → 16:14 UTC (44 min) |
| Data loss | None |

## Possible Causes

1. **Batch job without CPU limits** — reporting-service nightly batch promoted to prod afternoon run, consuming 14 vCPUs with no cap
2. **CPU requests too high on payment-service** — requested 2 vCPU per pod; cluster headroom < 12 vCPU
3. **Cluster not auto-scaled** — Cluster Autoscaler disabled for cost reduction, no new nodes provisioned
4. **HPA misconfigured** — target replica count scaled to 10 but max schedulable given requests was 4

## Troubleshooting Steps

1. Confirmed pending pods and scheduler reason
   ```bash
   kubectl get pods -n payments -l app=payment-service
   kubectl describe pod payment-svc-9g2k-rp01 -n payments | grep -A5 "Events"
   # Warning FailedScheduling: 0/6 nodes are available: 6 Insufficient cpu
   ```

2. Checked cluster-wide CPU allocation
   ```bash
   kubectl describe nodes | grep -A5 "Allocated resources"
   # All nodes: CPU requests at 95–100% of allocatable
   ```

3. Identified top CPU consumers
   ```bash
   kubectl top pods --all-namespaces --sort-by=cpu | head -15
   # reporting-batch-job-xxx   reporting   14200m CPU (no limits)
   ```

4. Verified Cluster Autoscaler status
   ```bash
   kubectl get deployment cluster-autoscaler -n kube-system
   kubectl logs -l app=cluster-autoscaler -n kube-system --tail=20
   # scale-up disabled: annotation cluster-autoscaler.kubernetes.io/safe-to-evict
   ```

5. Checked payment-service CPU requests vs. available headroom
   ```bash
   kubectl get deploy payment-service -n payments \
     -o jsonpath='{.spec.template.spec.containers[0].resources.requests}'
   # {"cpu":"2","memory":"1Gi"}  — 2 vCPU per pod × 6 = 12 vCPU needed, 0.4 available
   ```

## Resolution

1. Killed the runaway batch job to free cluster CPU immediately
   ```bash
   kubectl delete job reporting-batch-job-20260403 -n reporting
   ```

2. Confirmed freed CPU allowed pending pods to schedule within 90 seconds
   ```bash
   kubectl get pods -n payments -l app=payment-service
   # All 10 pods Running
   ```

3. Applied CPU limit to reporting batch jobs (max 4 vCPU per run) via manifest update

4. Re-enabled Cluster Autoscaler with conservative scale-up policy

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Pods Pending >10 min in prod | Escalate to platform team | #platform-support |
| Revenue service under-replicated during peak | Page EM + IC | #incident-response |
| Cluster Autoscaler not resolving within 5 min | Engage platform SRE for manual node addition | #platform-support |

## Post-Incident Notes

**Went well:**
- HPA correctly detected latency and attempted to scale
- Deleting the batch job immediately freed enough capacity

**Improve:**
- Batch jobs had no CPU limits — a single job could starve the entire cluster
- Cluster Autoscaler was disabled with no compensating capacity buffer
- No alert for `Pending` pods older than 5 minutes

**Action items:**
- [x] Killed batch job, confirmed pods scheduled
- [x] Applied CPU limit (4 vCPU max) to all reporting batch jobs
- [ ] Re-enable Cluster Autoscaler with appropriate min/max node config
- [ ] Add PodSchedulingFailed alert: pods Pending >5 min
- [ ] Review all batch/job workloads for missing resource limits

## Related Runbooks

- [[RB-006-pod-crash]]
- [[RB-003-high-cpu]]
