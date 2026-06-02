<!-- File: RB-004-high-cpu-usage.md -->
---
id: RB-004
title: High CPU Usage on Service or Node
service_scope: api-gateway, payment-service, auth-service, reporting-service
environment_scope: prod, staging
owner: SRE Team
severity_scope: high, critical
tags:
  - runbook
  - cpu
  - performance
  - infra
  - kubernetes
  - prod
created: 2026-06-02
updated: 2026-06-02
related_incidents:
  - "[[INC-007-high-cpu-payment-service]]"
  - "[[INC-013-k8s-pending-pods-resource-pressure]]"
  - "[[INC-021-nic-saturation-api-node]]"
---

# High CPU Usage on Service or Node

## Trigger

- PagerDuty alert: `*-CPUThrottled`, `*-HighCPU`, or `*-HighLatency` (latency caused by CPU saturation)
- Grafana: pod/node CPU usage sustained above 90% for >5 minutes
- Kubernetes: CPU throttling visible in `container_cpu_cfs_throttled_seconds_total`
- User reports: elevated latency or timeouts on specific service

**Desired outcome:** CPU usage stabilized below 70%, latency at pre-incident P99, no CPU throttling.

## Preconditions

- [ ] `kubectl` access to affected cluster and namespace
- [ ] SSH access to affected node (if node-level issue)
- [ ] Grafana access to CPU dashboards
- [ ] Identify affected service from alert payload

**Required tools:** kubectl, top/htop, Grafana, async-profiler or equivalent, thread dump utilities

## Commands and Checks

### 1. Confirm CPU saturation at pod level

```bash
kubectl top pods -n <namespace> -l app=<service-name> --sort-by=cpu
# Compare actual CPU vs. limits
kubectl get deploy <deployment> -n <namespace> \
  -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}'
# IF actual ≈ limit → pod is throttled
```

### 2. Check CPU throttling metrics

```bash
# In Grafana, check: container_cpu_cfs_throttled_periods_total
# Or via kubectl:
kubectl exec <pod-name> -n <namespace> -- cat /sys/fs/cgroup/cpu/cpu.stat
# Look for: nr_throttled (high number = active throttling)
```

### 3. Check if node-level or pod-level

```bash
kubectl top nodes
# IF a specific node is at 95%+ CPU:
kubectl describe node <node-name> | grep -A10 "Allocated resources"
# Check if CPU requests exceed 90% of allocatable
```

### 4. On the node (SSH) — identify top processes

```bash
ssh ec2-user@<node-ip>
top -bn1 | head -20
# Or for more detail:
ps aux --sort=-%cpu | head -15
# Look for: unexpected processes, runaway loops, batch jobs
```

### 5. Identify hot code path in the application

```bash
# For JVM services — capture thread dump:
kubectl exec <pod-name> -n <namespace> -- kill -3 1
kubectl logs <pod-name> -n <namespace> | grep -A10 "RUNNABLE"
# Or use async-profiler for CPU flame graph:
kubectl exec <pod-name> -n <namespace> -- /opt/profiler/profiler.sh -d 30 -f /tmp/cpu.html 1
kubectl cp <namespace>/<pod-name>:/tmp/cpu.html ./cpu-profile.html
```

### 6. Check for recent deployments correlating with CPU spike

```bash
kubectl rollout history deployment/<deployment> -n <namespace>
# Compare timestamp of last rollout with CPU spike start time
```

### 7. Check for runaway batch jobs or cron workloads

```bash
kubectl get jobs --all-namespaces --sort-by=.status.startTime | tail -10
kubectl top pods --all-namespaces --sort-by=cpu | head -10
# IF a batch job is consuming disproportionate CPU → candidate for kill/limit
```

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

### Option D: Rollback if recent deployment is the cause

```bash
kubectl rollout undo deployment/<deployment> -n <namespace> --to-revision=<N>
kubectl rollout status deployment/<deployment> -n <namespace> --timeout=180s
```

### Option E: Add request timeout (stop runaway computation)

```bash
# If the root cause is an algorithmic issue (e.g., regex backtracking):
kubectl set env deployment/<deployment> -n <namespace> REQUEST_TIMEOUT_MS=500
kubectl rollout restart deployment/<deployment> -n <namespace>
```

## Verification

- [ ] `kubectl top pods` shows CPU below 70% of limit
- [ ] No CPU throttling on Grafana (throttled periods metric flat)
- [ ] Service P99 latency returned to baseline
- [ ] No pending pods due to insufficient CPU on nodes

```bash
kubectl top pods -n <namespace> -l app=<service-name>
kubectl get pods -n <namespace> | grep Pending
# Expect: no Pending pods
curl -s -o /dev/null -w "%{http_code}" https://<service-endpoint>/health
# Expect: 200, response time < 200ms
```

## Rollback

```bash
# Undo CPU limit increase:
kubectl set resources deployment/<deployment> -n <namespace> \
  --limits=cpu=<original> --requests=cpu=<original>

# Undo scale-out:
kubectl scale deployment/<deployment> -n <namespace> --replicas=<original>

# Undo version rollback:
kubectl rollout undo deployment/<deployment> -n <namespace>

# Undo timeout env var:
kubectl set env deployment/<deployment> -n <namespace> REQUEST_TIMEOUT_MS-
```

## Escalation

| Condition | Escalate to | Channel |
|-----------|-------------|---------|
| CPU remains saturated after mitigation (15 min) | Senior on-call + service owner | PagerDuty |
| Node-level CPU at 100% affecting multiple services | Platform/SRE team | #platform-support |
| Algorithmic issue identified (regex, infinite loop) | Service development team | Direct page |
| Latency SLA breach >20 min | Engineering Manager + IC | #incident-response |

## Notes / Gotchas

- **Regex backtracking** is a common cause of sudden CPU saturation. See [[INC-007-high-cpu-payment-service]] — a catastrophic regex caused 11s match times.
- **CPU limits vs. requests:** Pods are throttled when they hit the *limit*, even if the node has spare CPU. If you're seeing throttling with node CPU at 50%, the limit is too low.
- **Batch jobs without limits** can starve the entire node. See [[INC-013-k8s-pending-pods-resource-pressure]] where a reporting job claimed 14 vCPUs.
- **Async-profiler** or equivalent is the fastest path to identifying the hot code path. Thread dumps alone may not show the issue if it's in native code.
- **NIC saturation can look like CPU saturation** if threads are blocked on I/O. Check network metrics if CPU profiling shows threads in I/O wait. See [[INC-021-nic-saturation-api-node]].
