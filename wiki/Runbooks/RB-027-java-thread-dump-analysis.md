---
id: RB-027
title: Java Application Thread Dump Analysis and Deadlock Resolution
service: "*"
related_services:
  - payment-service
  - order-service
  - auth-service
severity: SEV-2
environment: prod
category: performance
risk_level: low
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - java
  - thread-dump
  - deadlock
  - performance
  - jvm
  - prod
related_incidents:
  - "[[INC-042-log4j-appender-deadlock]]"
  - "[[INC-007-high-cpu-payment-service]]"
related_runbooks:
  - "[[RB-004-high-cpu-usage]]"
  - "[[RB-001-payment-gateway-oom-recovery]]"
related_guardrails: []
---

## Purpose

Capture and analyze JVM thread dumps to diagnose hung services, deadlocks, thread pool exhaustion, and high CPU caused by hot threads.

**Desired outcome:** Identify the blocking thread or contention pattern and resolve the hang/deadlock.

## Success Criteria

- Service responding to requests normally
- No BLOCKED/WAITING threads exceeding threshold
- Thread pool utilization below 80%
- No deadlock detected in thread dump
- Request latency at baseline

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any JVM-based service |
| Related services | payment-service, order-service, auth-service |
| Environments | prod, staging |
| Use when | Service unresponsive, high latency with normal CPU, suspected deadlock |
| Do NOT use when | Service is OOMKilled (use [[RB-001-payment-gateway-oom-recovery]] or [[RB-002-kubernetes-oom-remediation]]) |
| Risk level | Low (thread dump is non-destructive) |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl exec` access to affected pod
- [ ] JVM running with `jcmd` or `jstack` available
- [ ] Knowledge of expected thread pool sizes

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl exec` | Pod access for thread dump | Cluster admin |
| `jcmd` / `jstack` / `kill -3` | Thread dump capture | Pod exec |
| Thread dump analyzer | Visualization and deadlock detection | Local tool |

## Trigger

- Service unresponsive (HTTP timeouts) but pod shows Running
- Liveness probe passing (TCP) but readiness failing (HTTP)
- High latency with CPU not maxed out (threads blocked, not computing)
- Alert: `*-ThreadPoolExhausted`, `*-ServiceHung`

## Triage

1. Confirm service is hung (not crashed)
   ```bash
   kubectl get pod <pod> -n <namespace>
   # Running, but:
   curl --max-time 5 http://<pod-ip>:8080/health
   # Times out or very slow
   ```

2. Quick CPU check — hung threads don't consume CPU
   ```bash
   kubectl top pod <pod> -n <namespace>
   # Low/moderate CPU + unresponsive = thread contention
   # High CPU + unresponsive = hot loop (use [[RB-004-high-cpu-usage]])
   ```

## Investigation

1. **Capture thread dump (method 1: kill -3)**
   ```bash
   kubectl exec <pod> -n <namespace> -- kill -3 1
   kubectl logs <pod> -n <namespace> | grep -A100 "Full thread dump"
   ```

2. **Capture thread dump (method 2: jcmd)**
   ```bash
   kubectl exec <pod> -n <namespace> -- jcmd 1 Thread.print > /tmp/tdump.txt
   kubectl cp <namespace>/<pod>:/tmp/tdump.txt ./tdump-$(date +%s).txt
   ```

3. **Check for deadlocks**
   ```bash
   kubectl exec <pod> -n <namespace> -- jcmd 1 Thread.print | grep -A5 "Found.*deadlock"
   # What to look for: "Found one Java-level deadlock"
   ```

4. **Count thread states**
   ```bash
   kubectl exec <pod> -n <namespace> -- jcmd 1 Thread.print | grep "java.lang.Thread.State" | sort | uniq -c
   # What to look for: many BLOCKED or WAITING threads
   ```

5. **Identify blocking thread**
   ```bash
   kubectl exec <pod> -n <namespace> -- jcmd 1 Thread.print | grep -B5 "BLOCKED" | grep "locked"
   # What to look for: which lock/monitor is contended
   ```

6. **Decision point:**
   - IF deadlock found → proceed to Mitigation Option A
   - IF thread pool exhausted (all threads WAITING on I/O) → proceed to Mitigation Option B
   - IF single lock contention → proceed to Mitigation Option C

## Mitigation

### Option A: Deadlock — restart pod (only fix for true deadlock)

```bash
kubectl delete pod <pod> -n <namespace>
# New pod will be created by deployment controller
# File bug with thread dump attached for code fix
```

### Option B: Thread pool exhausted — scale or increase pool

```bash
# Increase thread pool:
kubectl set env deployment/<name> -n <namespace> SERVER_TOMCAT_MAX_THREADS=400
kubectl rollout restart deployment/<name> -n <namespace>
# Or scale horizontally:
kubectl scale deployment/<name> -n <namespace> --replicas=<current+2>
```

### Option C: Lock contention — restart to clear stuck thread

```bash
kubectl rollout restart deployment/<name> -n <namespace>
# If contention is on a database lock, check [[RB-005-database-timeout-connection-exhaustion]]
```

**After mitigation:** Verify service responding within normal latency.

## Verification

- [ ] Service health endpoint responding in <200ms
- [ ] No BLOCKED threads in new thread dump
- [ ] Request processing normally
- [ ] Thread pool utilization below 80%

```bash
curl -s -o /dev/null -w "%{time_total}" http://<service>:8080/health
# Expected: <0.2s
```

## Failure Signals

- Service hangs again after restart (persistent deadlock pattern)
- Thread pool exhaustion recurs under normal load
- Underlying lock holder is an external dependency (DB, cache)

## Rollback

1. **If thread pool increase caused OOM:** Revert to original value
2. **If scale-out caused resource pressure:** Scale back down

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Deadlock recurring after restart | Service owner (code fix needed) | Direct page | 15 min |
| All request threads blocked on DB | DBA team | #data-eng | 10 min |
| Cannot capture thread dump | Platform team | #platform-support | 10 min |

## Notes

- **Thread dumps are safe and non-destructive.** Capture multiple (3 dumps, 10s apart) to identify persistent blocks vs. transient waits.
- **kill -3 dumps to stdout/stderr** — check container logs, not a file.
- **BLOCKED vs WAITING:** BLOCKED = competing for a monitor. WAITING = waiting for notification (may be normal I/O wait).
- **Log4j deadlocks** look like the application is completely frozen with low CPU. See [[INC-042-log4j-appender-deadlock]].

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Deploy test service with intentional synchronized block in staging, capture and analyze thread dump.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
