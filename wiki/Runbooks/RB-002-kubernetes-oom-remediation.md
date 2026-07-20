---
id: RB-002
title: Kubernetes OOM / OOMKilled Remediation
service: "*"
related_services:
  - api-gateway
  - auth-service
  - payment-service
severity: SEV-2
environment: prod
category: resource-exhaustion
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - kubernetes
  - oom
  - memory
  - container
  - prod
related_incidents:
  - "[[INC-001-payment-service-oom-crash]]"
  - "[[INC-002-k8s-oom-api-pod]]"
  - "[[INC-016-memory-pressure-app-node]]"
related_runbooks:
  - "[[RB-001-payment-gateway-oom-recovery]]"
  - "[[RB-007-pod-crash-investigation]]"
related_guardrails: []
---

## Purpose

Generic runbook for diagnosing and remediating OOMKilled events on any Kubernetes service, covering memory limit increases, rollbacks, and horizontal scaling.

**Desired outcome:** Affected pods running stably with memory usage below 70% of limit and error rate at pre-incident baseline.

## Success Criteria

Before closing the incident or declaring the runbook complete, ALL of the following must be true:

- All pods in `Running` state with 0 restarts in last 10 minutes
- Memory usage stable below 70% of limit on Grafana
- Application error rate returned to baseline (<0.1% for most services)
- No new OOMKilled events in `kubectl get events`
- Health endpoint returning 200

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any Kubernetes service experiencing OOM |
| Related services | api-gateway, auth-service, payment-service |
| Environments | prod, staging |
| Use when | Pods are OOMKilled or CrashLoopBackOff with exit code 137 |
| Do NOT use when | Crash is not OOM-related (exit code ≠ 137, no OOMKilled in describe) |
| Risk level | Medium |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to affected cluster and namespace
- [ ] Grafana access to container memory dashboards
- [ ] Knowledge of which service is affected (from alert payload)
- [ ] On-call role confirmed in PagerDuty before making changes

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Pod/deployment operations | Cluster admin |
| Grafana | Memory trend analysis | Read access |
| Sentry/APM | Application error context | Read access |
| Eclipse MAT | Heap dump analysis (optional) | Local tool |

## Trigger

- Alert: `*-PodOOMKilled` or `*-PodCrashLooping` with OOM reason
- Symptom: `OOMKilled` visible in `kubectl describe pod` output
- Metric: Container memory usage at 100% of limit followed by pod restart
- Symptom: `java.lang.OutOfMemoryError` or equivalent in application logs

## Triage

1. Confirm OOMKilled state
   ```bash
   kubectl get pods -n <namespace> -l app=<service-name>
   kubectl describe pod <pod-name> -n <namespace> | grep -A5 "Last State"
   # What to look for: Reason: OOMKilled, Exit code: 137
   ```

2. Assess blast radius — single pod or cluster-wide
   ```bash
   kubectl get pods --all-namespaces --field-selector status.phase!=Running | grep OOMKilled
   # IF multiple services → likely node-level pressure (see INC-016 pattern)
   # IF single service → application-level issue
   ```

3. Wrong symptoms? → Try [[RB-007-pod-crash-investigation]]

## Investigation

1. **Check current memory limits**
   ```bash
   kubectl get deploy <deployment> -n <namespace> \
     -o jsonpath='{.spec.template.spec.containers[0].resources}'
   # Record: requests.memory and limits.memory
   ```

2. **Check actual memory usage** (if pods are running)
   ```bash
   kubectl top pods -n <namespace> -l app=<service-name> --sort-by=memory
   # What to look for: actual usage at 90%+ of limit = OOM imminent
   ```

3. **Check memory trend on Grafana**
   ```bash
   # Open dashboard for affected service → container memory panel
   # What to look for: Linear growth = memory leak; sudden spike = load-induced
   ```

4. **Attempt to capture heap dump** (JVM services)
   ```bash
   kubectl exec <pod-name> -n <namespace> -- ls /tmp/heapdump.hprof 2>/dev/null
   # IF exists, copy it out:
   kubectl cp <namespace>/<pod-name>:/tmp/heapdump.hprof ./heapdump-$(date +%s).hprof
   ```

5. **Decision point:**
   - IF single service, stable growth → memory leak → proceed to Mitigation Option A then Option B
   - IF single service, sudden spike → load-induced → proceed to Mitigation Option A then Option C
   - IF multiple services OOMKilled → node-level pressure → escalate to Platform/SRE
   - IF unclear → escalate (see Escalation section)

## Mitigation

### Option A: Increase memory limit (buys time)

```bash
kubectl set resources deployment/<deployment> -n <namespace> \
  --limits=memory=<current-limit × 1.5 or 2> \
  --requests=memory=<current-request × 1.5>
kubectl rollout restart deployment/<deployment> -n <namespace>
kubectl rollout status deployment/<deployment> -n <namespace> --timeout=180s
```

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
# Useful if OOM is load-induced — more pods = less memory per pod
```

**After mitigation:** Monitor for 10–15 minutes. Pods should stabilize at <70% of new limit before declaring resolved.

## Verification

- [ ] All pods in `Running` state with 0 restarts in last 10 minutes
- [ ] Memory usage stable below 70% of limit on Grafana
- [ ] Application error rate returned to baseline (<0.1%)
- [ ] No new OOMKilled events in `kubectl get events -n <namespace>`
- [ ] Health endpoint returning 200

```bash
kubectl get pods -n <namespace> -l app=<service-name>
kubectl top pods -n <namespace> -l app=<service-name>
curl -s -o /dev/null -w "%{http_code}" https://<service-endpoint>/health
# Expected: 200
```

## Failure Signals

If the mitigation did NOT work, you will observe one or more of the following:

- Pods still growing toward new memory limit within 15 minutes
- New OOMKilled events despite increased limits
- Error rate does not decrease within 5 minutes
- Pods enter CrashLoopBackOff again after restart
- Node-level memory pressure alerts firing

**If any failure signal is present after mitigation:** Do NOT repeat the same step. Proceed to Rollback or Escalation immediately.

## Rollback

1. **Undo memory limit change:**
   ```bash
   kubectl set resources deployment/<deployment> -n <namespace> \
     --limits=memory=<original-limit> --requests=memory=<original-request>
   ```

2. **Undo version rollback** (if you rolled back too far):
   ```bash
   kubectl rollout undo deployment/<deployment> -n <namespace>
   ```

3. **Undo scale-out:**
   ```bash
   kubectl scale deployment/<deployment> -n <namespace> --replicas=<original-count>
   ```

4. Notify #incident-response: "Rollback executed — mitigation did not stabilize, escalating."

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| OOM continues after memory increase + restart (15 min) | Senior on-call + service owner | PagerDuty escalation | 5 min response |
| Multiple services OOMKilled simultaneously | Platform/SRE team | #platform-support | 10 min response |
| Heap dump analysis required (>30 min investigation) | Service owner / dev team | Direct page | 15 min response |
| Customer-facing SEV-1 with no fix in 30 min | Engineering Manager + IC | #incident-response | Immediate |

## Notes

- **JVM services:** Container limit must be higher than `-Xmx` to account for metaspace, thread stacks, and off-heap allocations. Rule of thumb: container limit = Xmx × 1.3.
- **Node-level vs. pod-level OOM:** If the kernel OOM killer fires before Kubernetes limits are hit, the issue is node memory pressure — check kubelet eviction thresholds.
- **Cache-related OOMs:** 3 out of 4 historical OOM incidents traced to unbounded caches. Always check cache sizes first.
- **Don't increase limits beyond node capacity.** Check `kubectl describe node` for allocatable memory before setting new limits.
- This runbook may be invoked from [[RB-007-pod-crash-investigation]] if CrashLoopBackOff root cause is OOM.
- See also: [[INC-001-payment-service-oom-crash]], [[INC-002-k8s-oom-api-pod]], [[INC-016-memory-pressure-app-node]]

## Maintenance

- **Last tested:** 2026-06-02
- **Review cycle:** Quarterly
- **Next review:** 2026-09-02
- **Test method:** Simulate OOM by deploying a memory stress container in staging namespace and executing runbook steps.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-02 | SRE Team | Initial publication |
| 2026-06-12 | SRE Team | Migrated to new runbook template format |
