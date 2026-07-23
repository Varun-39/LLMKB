---
id: INC-090
title: Overly Aggressive Liveness Probe Causing Healthy Pod Restart Loop
severity: SEV-2
service: auth-service
environment: prod
category: degradation
date: 2026-04-21
duration: "35m"
tags:
  - incident
  - kubernetes
  - liveness-probe
  - restart-loop
  - auth-service
  - prod
error_family: unknown
resolution_runbook: RB-007
resolution_outcome: resolved
---

## Summary

A platform team tightened liveness probe timeouts across all services during a reliability sprint (timeout reduced from 5s to 1s, failureThreshold from 6 to 2). The auth-service `/health` endpoint performs a lightweight DB ping that occasionally takes 1.5–2 seconds under load. The tightened probe began killing healthy pods during traffic spikes, creating a restart loop that degraded authentication for 35 minutes.

## Symptoms

- auth-service pod restarts climbing: 8 restarts per pod in 30 minutes
- `kubectl get pods -n auth`: all pods showing high `RESTARTS` count
- auth-service error rate: 12% (requests hitting restarting pods)
- PagerDuty: `auth-service high error rate` SEV-2 fired

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~5,000 users experiencing auth failures |
| Services degraded | auth-service, all services requiring authentication |
| Revenue impact | ~$3.4K (checkout abandonment) |
| Duration | 18:00 → 18:35 UTC (35 min) |
| Data loss | None |
| SLA breach | No |
| Customer comms | Status page: "Users may experience login issues" |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 17:50 | Platform deploys probe tightening across all services |
| 18:00 | Traffic spike hits auth-service |
| 18:02 | Liveness probes begin timing out on 1.5s health checks |
| 18:05 | First pod restarts |
| 18:10 | Error rate alert fires |
| 18:15 | On-call identifies probe configuration |
| 18:35 | Probe reverted; pod restarts stopped |

## Diagnosis

1. Checked restart count and reason:
   ```bash
   kubectl describe pod auth-service-xxxx -n auth | grep -A5 "Last State"
   # Last State: Terminated, Reason: Error, Exit Code: 137 (SIGKILL from liveness)
   ```
2. Checked liveness probe config:
   ```bash
   kubectl get pod auth-service-xxxx -n auth -o yaml | grep -A10 livenessProbe
   # timeoutSeconds: 1, failureThreshold: 2  — 2 failures = kill in 2s
   ```
3. Confirmed /health endpoint latency under load:
   ```bash
   kubectl exec -n auth deploy/auth-service -- time curl -s localhost:8080/health
   # real 1.62s  — exceeds 1s timeout
   ```

## Resolution

1. **Mitigate:** Reverted liveness probe to previous settings:
   ```bash
   kubectl patch deployment auth-service -n auth --type=json \
     -p='[{"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/timeoutSeconds","value":5},{"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/failureThreshold","value":6}]'
   ```
2. **Pod restarts stopped** within 2 minutes of patch
3. **Fix:** auth-service /health endpoint refactored to avoid DB query (use cached state instead)

## Post-Incident Review

**What went well:**
- Root cause identified quickly — probe config is visible in kubectl describe

**What needs improvement:**
- No per-service health endpoint latency profiling before applying global probe changes
- Liveness probe changes deployed to all services simultaneously

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Profile /health endpoint latency for each service before tightening probes | Platform | 2026-04-28 | Open |
| Roll probe changes per service with 24h soak period | Platform | 2026-04-28 | Open |
| Refactor /health to not block on DB query | Backend | 2026-04-28 | Open |

## Links

- Runbooks: [[RB-007-pod-crash-investigation]]
- Related incidents: [[INC-003-k8s-crashloopbackoff-auth]], [[INC-002-k8s-oom-api-pod]]
