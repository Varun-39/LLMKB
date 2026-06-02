<!-- File: RB-002-kubernetes-oom-remediation.md -->
---
id: RB-002
title: Kubernetes OOM / OOMKilled Remediation
service_scope: api-gateway, auth-service, payment-service
environment_scope: prod, staging
owner: SRE Team
severity_scope: high, critical
tags:
  - runbook
  - kubernetes
  - oom
  - memory
  - container
  - prod
created: 2026-06-02
updated: 2026-06-02
related_incidents:
  - "[[INC-001-payment-service-oom-crash]]"
  - "[[INC-002-k8s-oom-api-pod]]"
  - "[[INC-016-memory-pressure-app-node]]"
---

# Kubernetes OOM / OOMKilled Remediation

## Trigger

- PagerDuty alert: `*-PodOOMKilled` or `*-PodCrashLooping` with OOM reason
- Kubernetes event: `OOMKilled` visible in pod describe output
- Grafana: container memory usage at 100% of limit followed by pod restart
- Sentry / application logs: `java.lang.OutOfMemoryError` or equivalent language-specific OOM

**Desired outcome:** Affected pods are running stably with memory usage below 70% of limit and error rate at pre-incident baseline.

## Preconditions

- [ ] `kubectl` access to affected cluster and namespace
- [ ] Grafana access to container memory dashboards
- [ ] Knowledge of which service is affected (from alert payload)
- [ ] Confirm you are on the on-call rota before making changes

**Required tools:** kubectl, Grafana, Sentry/APM dashboard, optional: Eclipse MAT for heap dump analysis

## Commands and Checks

### 1. Confirm OOMKilled state

```bash
kubectl get pods -n <namespace> -l app=<service-name>
kubectl describe pod <pod-name> -n <namespace> | grep -A5 "Last State"
# Look for: Reason: OOMKilled
# Note the exit code (137 = SIGKILL from OOM killer)
```

### 2. Check current memory limits

```bash
kubectl get deploy <deployment> -n <namespace> \
  -o jsonpath='{.spec.template.spec.containers[0].resources}'
# Record: requests.memory and limits.memory
```

### 3. Check actual memory usage (if pods are running)

```bash
kubectl top pods -n <namespace> -l app=<service-name> --sort-by=memory
# Compare actual usage vs. limit — if usage is 90%+ of limit, OOM is imminent
```

### 4. Check if issue is isolated or cluster-wide

```bash
kubectl get pods --all-namespaces --field-selector status.phase!=Running | grep OOMKilled
# IF multiple services OOMKilled → likely node-level pressure (see INC-016 pattern)
# IF single service → likely application-level leak or undersized limit
```

### 5. Check memory trend on Grafana

- Open dashboard for affected service → container memory panel
- IF linear growth over time → memory leak (cache, connection objects, etc.)
- IF sudden spike → load-induced, check traffic volume

### 6. Attempt to capture heap dump (JVM services)

```bash
# Only if pod is still running (CrashLoopBackOff with brief uptime):
kubectl exec <pod-name> -n <namespace> -- ls /tmp/heapdump.hprof 2>/dev/null
# IF exists: copy it out for analysis
kubectl cp <namespace>/<pod-name>:/tmp/heapdump.hprof ./heapdump-$(date +%s).hprof
```

## Mitigation

### Option A: Increase memory limit (buys time)

```bash
kubectl set resources deployment/<deployment> -n <namespace> \
  --limits=memory=<current-limit × 1.5 or 2> \
  --requests=memory=<current-request × 1.5>
kubectl rollout restart deployment/<deployment> -n <namespace>
kubectl rollout status deployment/<deployment> -n <namespace> --timeout=180s
```

**Decision point:**
- IF pods stabilize at <70% of new limit → success, schedule root cause investigation
- IF pods still growing toward new limit → proceed to Option B

### Option B: Rollback to last known good version

```bash
kubectl rollout history deployment/<deployment> -n <namespace>
# Identify last revision that ran without OOM
kubectl rollout undo deployment/<deployment> -n <namespace> --to-revision=<N>
kubectl rollout status deployment/<deployment> -n <namespace> --timeout=180s
```

### Option C: Scale horizontally (distribute memory load)

```bash
kubectl scale deployment/<deployment> -n <namespace> --replicas=<current+2>
# Useful if OOM is load-induced (more pods = less memory per pod)
```

## Verification

- [ ] All pods in `Running` state with 0 restarts in last 10 minutes
- [ ] Memory usage stable below 70% of limit on Grafana
- [ ] Application error rate returned to baseline (<0.1% for most services)
- [ ] No new OOMKilled events in `kubectl get events -n <namespace>`

```bash
kubectl get pods -n <namespace> -l app=<service-name>
kubectl top pods -n <namespace> -l app=<service-name>
curl -s -o /dev/null -w "%{http_code}" https://<service-endpoint>/health
# Expect: 200
```

## Rollback

If mitigation made things worse:

```bash
# Undo memory limit change
kubectl set resources deployment/<deployment> -n <namespace> \
  --limits=memory=<original-limit> --requests=memory=<original-request>

# Undo version rollback (if you rolled back too far)
kubectl rollout undo deployment/<deployment> -n <namespace>

# Undo scale-out
kubectl scale deployment/<deployment> -n <namespace> --replicas=<original-count>
```

Notify #incident-response: "Rollback executed — mitigation did not stabilize, escalating."

## Escalation

| Condition | Escalate to | Channel |
|-----------|-------------|---------|
| OOM continues after memory increase + restart (15 min) | Senior on-call + service owner | PagerDuty escalation |
| Multiple services OOMKilled simultaneously | Platform/SRE team | #platform-support |
| Heap dump analysis required (>30 min investigation) | Service owner / dev team | Direct page |
| Customer-facing SEV-1 with no fix in 30 min | Engineering Manager + IC | #incident-response |

## Notes / Gotchas

- **JVM services:** Container limit must be higher than `-Xmx` to account for metaspace, thread stacks, and off-heap allocations. Rule of thumb: container limit = Xmx × 1.3.
- **Node-level vs. pod-level OOM:** If the kernel OOM killer fires before Kubernetes limits are hit, the issue is node memory pressure — see [[INC-016-memory-pressure-app-node]] and check kubelet eviction thresholds.
- **Cache-related OOMs:** 3 out of 4 historical OOM incidents in this vault traced to unbounded caches. Always check cache sizes first: [[INC-001-payment-service-oom-crash]], [[INC-002-k8s-oom-api-pod]].
- **Don't increase limits beyond node capacity.** Check `kubectl describe node` for allocatable memory before setting new limits.
- This runbook may be invoked from [[RB-007-pod-crash-investigation]] if CrashLoopBackOff root cause is OOM.
