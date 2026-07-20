---
id: RB-004
title: High CPU Usage on Service or Node
service: "*"
related_services:
  - api-gateway
  - payment-service
  - auth-service
  - reporting-service
severity: SEV-2
environment: prod
category: performance
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - cpu
  - performance
  - infra
  - kubernetes
  - prod
related_incidents:
  - "[[INC-007-high-cpu-payment-service]]"
  - "[[INC-013-k8s-pending-pods-resource-pressure]]"
related_runbooks:
  - "[[RB-007-pod-crash-investigation]]"
  - "[[RB-008-network-saturation-throughput]]"
related_guardrails: []
---

## Purpose

Diagnose and remediate sustained high CPU usage or CPU throttling on a Kubernetes service or node, covering identification of hot code paths, runaway jobs, and safe stabilization.

**Desired outcome:** CPU usage stabilized below 70%, latency at pre-incident P99, no CPU throttling.

## Success Criteria

Before closing the incident or declaring the runbook complete, ALL of the following must be true:

- `kubectl top pods` shows CPU below 70% of limit
- No CPU throttling on Grafana (throttled periods metric flat)
- Service P99 latency returned to baseline
- No pending pods due to insufficient CPU on nodes
- No active alerts for this service for at least 15 minutes

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any Kubernetes service with high CPU |
| Related services | api-gateway, payment-service, auth-service, reporting-service |
| Environments | prod, staging |
| Use when | `*-CPUThrottled`, `*-HighCPU`, or `*-HighLatency` alert, or sustained >90% CPU for 5+ min |
| Do NOT use when | High CPU is expected (batch processing during maintenance window) |
| Risk level | Medium |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to affected cluster and namespace
- [ ] SSH access to affected node (if node-level issue)
- [ ] Grafana access to CPU dashboards
- [ ] Identify affected service from alert payload

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Pod/deployment operations | Cluster admin |
| Grafana | CPU trend and throttling metrics | Read access |
| SSH + `top`/`htop` | Node-level process inspection | sudo access |
| async-profiler | CPU flame graph generation | Pod exec access |
| Thread dump utilities | JVM thread analysis | Pod exec access |

## Trigger

- Alert: `*-CPUThrottled`, `*-HighCPU`, or `*-HighLatency` (latency caused by CPU saturation)
- Metric: Pod/node CPU usage sustained above 90% for >5 minutes
- Metric: CPU throttling visible in `container_cpu_cfs_throttled_seconds_total`
- Symptom: Elevated latency or timeouts on specific service

## Triage

1. Confirm CPU saturation at pod level
   ```bash
   kubectl top pods -n <namespace> -l app=<service-name> --sort-by=cpu
   kubectl get deploy <deployment> -n <namespace> \
     -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}'
   # What to look for: actual CPU ≈ limit = pod is throttled
   ```

2. Assess blast radius — pod-level or node-level
   ```bash
   kubectl top nodes
   # What to look for: specific node at 95%+ CPU
   ```

3. Wrong symptoms? → Try [[RB-007-pod-crash-investigation]]

## Investigation

1. **Check CPU throttling metrics**
   ```bash
   kubectl exec <pod-name> -n <namespace> -- cat /sys/fs/cgroup/cpu/cpu.stat
   # What to look for: high nr_throttled = active throttling
   ```

2. **On the node — identify top processes** (if node-level)
   ```bash
   ssh ec2-user@<node-ip>
   top -bn1 | head -20
   ps aux --sort=-%cpu | head -15
   # What to look for: unexpected processes, runaway loops, batch jobs
   ```

3. **Identify hot code path in the application**
   ```bash
   # JVM — capture thread dump:
   kubectl exec <pod-name> -n <namespace> -- kill -3 1
   kubectl logs <pod-name> -n <namespace> | grep -A10 "RUNNABLE"
   # Or use async-profiler:
   kubectl exec <pod-name> -n <namespace> -- /opt/profiler/profiler.sh -d 30 -f /tmp/cpu.html 1
   kubectl cp <namespace>/<pod-name>:/tmp/cpu.html ./cpu-profile.html
   ```

4. **Correlate with recent deployments**
   ```bash
   kubectl rollout history deployment/<deployment> -n <namespace>
   # What to look for: new revision timestamp matching CPU spike start
   ```

5. **Check for runaway batch jobs or cron workloads**
   ```bash
   kubectl get jobs --all-namespaces --sort-by=.status.startTime | tail -10
   kubectl top pods --all-namespaces --sort-by=cpu | head -10
   # What to look for: a batch job consuming disproportionate CPU
   ```

6. **Decision point:**
   - IF runaway batch job identified → proceed to Mitigation Option A
   - IF CPU limit too low for normal load → proceed to Mitigation Option B
   - IF load-induced spike → proceed to Mitigation Option C
   - IF recent deployment correlates → proceed to Mitigation Option D
   - IF algorithmic issue (regex, infinite loop) → proceed to Mitigation Option E
   - IF unclear → escalate (see Escalation section)

## Mitigation

### Option A: Kill runaway batch job (if identified)

```bash
kubectl delete job <job-name> -n <namespace>
# Or kill specific pod:
kubectl delete pod <pod-name> -n <namespace>
```

### Option B: Increase CPU limits (buys time)

```bash
kubectl set resources deployment/<deployment> -n <namespace> \
  --limits=cpu=<current × 2> --requests=cpu=<current × 1.5>
kubectl rollout restart deployment/<deployment> -n <namespace>
```

### Option C: Scale horizontally (distribute CPU load)

```bash
kubectl scale deployment/<deployment> -n <namespace> --replicas=<current + 2>
```

### Option D: Rollback (if recent deployment is the cause)

```bash
kubectl rollout undo deployment/<deployment> -n <namespace> --to-revision=<N>
kubectl rollout status deployment/<deployment> -n <namespace> --timeout=180s
```

### Option E: Add request timeout (stop runaway computation)

```bash
kubectl set env deployment/<deployment> -n <namespace> REQUEST_TIMEOUT_MS=500
kubectl rollout restart deployment/<deployment> -n <namespace>
```

**After mitigation:** Monitor for 10–15 minutes — CPU below 70%, P99 latency at baseline, no throttling.

## Verification

- [ ] `kubectl top pods` shows CPU below 70% of limit
- [ ] No CPU throttling on Grafana (throttled periods metric flat)
- [ ] Service P99 latency returned to baseline
- [ ] No pending pods due to insufficient CPU on nodes
- [ ] Health endpoint returning 200 with response time < 200ms

```bash
kubectl top pods -n <namespace> -l app=<service-name>
kubectl get pods -n <namespace> | grep Pending
# Expected: no Pending pods
curl -s -o /dev/null -w "%{http_code}" https://<service-endpoint>/health
# Expected: 200
```

## Failure Signals

If the mitigation did NOT work, you will observe one or more of the following:

- CPU usage remains at or returns to >90% within 5 minutes
- Throttling metrics continue to rise on Grafana
- P99 latency does not improve or worsens
- New pods enter Pending state due to resource pressure
- Downstream services begin timing out

**If any failure signal is present after mitigation:** Do NOT repeat the same step. Proceed to Rollback or Escalation immediately.

## Rollback

1. **Undo CPU limit increase:**
   ```bash
   kubectl set resources deployment/<deployment> -n <namespace> \
     --limits=cpu=<original> --requests=cpu=<original>
   ```

2. **Undo scale-out:**
   ```bash
   kubectl scale deployment/<deployment> -n <namespace> --replicas=<original>
   ```

3. **Undo version rollback:**
   ```bash
   kubectl rollout undo deployment/<deployment> -n <namespace>
   ```

4. **Undo timeout env var:**
   ```bash
   kubectl set env deployment/<deployment> -n <namespace> REQUEST_TIMEOUT_MS-
   ```

5. Notify #incident-response: "Rollback executed — escalating."

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| CPU remains saturated after mitigation (15 min) | Senior on-call + service owner | PagerDuty | 5 min response |
| Node-level CPU at 100% affecting multiple services | Platform/SRE team | #platform-support | 10 min response |
| Algorithmic issue identified (regex, infinite loop) | Service development team | Direct page | 15 min response |
| Latency SLA breach >20 min | Engineering Manager + IC | #incident-response | Immediate |

## Notes

- **Regex backtracking** is a common cause of sudden CPU saturation. See [[INC-007-high-cpu-payment-service]] — a catastrophic regex caused 11s match times.
- **CPU limits vs. requests:** Pods are throttled when they hit the *limit*, even if the node has spare CPU. If you're seeing throttling with node CPU at 50%, the limit is too low.
- **Batch jobs without limits** can starve the entire node. See [[INC-013-k8s-pending-pods-resource-pressure]] where a reporting job claimed 14 vCPUs.
- **Async-profiler** or equivalent is the fastest path to identifying the hot code path. Thread dumps alone may not show the issue if it's in native code.
- **NIC saturation can look like CPU saturation** if threads are blocked on I/O. Check network metrics if CPU profiling shows threads in I/O wait. See [[RB-008-network-saturation-throughput]] and [[INC-021-nic-saturation-api-node]].
- See also: [[INC-007-high-cpu-payment-service]], [[INC-013-k8s-pending-pods-resource-pressure]]

## Maintenance

- **Last tested:** 2026-06-02
- **Review cycle:** Quarterly
- **Next review:** 2026-09-02
- **Test method:** Run CPU stress test (`stress-ng --cpu 4`) in staging pod, execute runbook investigation and mitigation steps.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-02 | SRE Team | Initial publication |
| 2026-06-12 | SRE Team | Migrated to new runbook template format |
