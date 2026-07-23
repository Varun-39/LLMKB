---
id: INC-013
title: Pods Stuck Pending — Cluster CPU Capacity Exhausted
severity: SEV-2
service: payment-service
environment: prod
category: degradation
date: 2026-04-03
duration: "44m"
detection_gap: "3m"
tags:
  - incident
  - kubernetes
  - scheduling
  - cpu
  - capacity
  - high
  - prod
  - payments
error_family: high-cpu
resolution_runbook: RB-004
resolution_outcome: resolved
---

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
| SLA breach | No — degradation, not full outage |
| Customer comms | N/A — latency degradation, no status page update |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 15:30 | HPA triggered scale-out; 6 new pods enter Pending |
| 15:33 | Alert fired: `PaymentService-HighLatency` |
| 15:34 | On-call acknowledged (Priya Sharma) |
| 15:38 | Pending pods confirmed — scheduler reports insufficient CPU |
| 15:42 | Identified reporting batch job consuming 14 vCPUs with no limit |
| 15:45 | Batch job deleted to free cluster CPU |
| 15:47 | Pending pods scheduled within 90 seconds |
| 16:14 | Latency fully normalized, incident closed |

## Diagnosis

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

1. **Mitigate:** Killed the runaway batch job to free cluster CPU immediately
   ```bash
   kubectl delete job reporting-batch-job-20260403 -n reporting
   ```

2. **Fix:** Applied CPU limit to reporting batch jobs and re-enabled Cluster Autoscaler
   ```bash
   # CPU limit applied (max 4 vCPU per run) via manifest update
   # Cluster Autoscaler re-enabled with conservative scale-up policy
   ```

3. **Verify:** Confirmed freed CPU allowed pending pods to schedule
   ```bash
   kubectl get pods -n payments -l app=payment-service
   # All 10 pods Running
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Pods Pending >10 min in prod | Escalate to platform team | #platform-support |
| Revenue service under-replicated during peak | Page EM + IC | #incident-response |
| Cluster Autoscaler not resolving within 5 min | Engage platform SRE for manual node addition | #platform-support |

## Post-Incident Review

**What went well:**
- HPA correctly detected latency and attempted to scale
- Deleting the batch job immediately freed enough capacity

**What needs improvement:**
- Batch jobs had no CPU limits — a single job could starve the entire cluster
- Cluster Autoscaler was disabled with no compensating capacity buffer
- No alert for `Pending` pods older than 5 minutes

**Contributing factors (beyond root cause):**
- Reporting batch job promoted from nightly to afternoon run without resource review
- Cluster Autoscaler disabled for cost reduction without capacity buffer
- CPU requests too high on payment-service (2 vCPU per pod)

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Kill batch job, confirm pods scheduled | Priya Sharma | 2026-04-03 | Done |
| Apply CPU limit (4 vCPU max) to all reporting batch jobs | James Okafor | 2026-04-03 | Done |
| Re-enable Cluster Autoscaler with appropriate min/max node config | Platform team | 2026-04-17 | Open |
| Add PodSchedulingFailed alert: pods Pending >5 min | SRE team | 2026-04-17 | Open |
| Review all batch/job workloads for missing resource limits | Platform team | 2026-04-17 | Open |

## Links

- Runbooks: [[RB-004-high-cpu-usage]], [[RB-007-pod-crash-investigation]]
- Related incidents: [[INC-004-k8s-node-notready]], [[INC-007-high-cpu-payment-service]]
- PR/commit: N/A
- Post-mortem doc: N/A
