---
id: RB-032
title: Memory Leak Diagnosis and Containment
service: "*"
related_services:
  - payment-service
  - realtime-service
  - api-gateway
severity: SEV-2
environment: prod
category: resource-exhaustion
risk_level: medium
estimated_duration: "25m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - memory
  - leak
  - heap
  - profiling
  - oom
  - prod
related_incidents:
  - "[[INC-001-payment-service-oom-crash]]"
  - "[[INC-058-goroutine-leak-websocket-service]]"
  - "[[INC-016-memory-pressure-app-node]]"
related_runbooks:
  - "[[RB-001-payment-gateway-oom-recovery]]"
  - "[[RB-002-kubernetes-oom-remediation]]"
related_guardrails: []
---

## Purpose

Diagnose memory leaks in production services by capturing heap dumps, analyzing growth patterns, and containing the leak until a fix is deployed.

**Desired outcome:** Leak identified (root cause class/object), service stabilized with temporary mitigation, fix path documented.

## Success Criteria

- Memory growth pattern identified (linear growth confirms leak)
- Root cause object/allocation identified via profiling
- Service stabilized below 70% memory limit
- Temporary mitigation in place (restart schedule or increased limit)
- Bug filed with heap dump and analysis attached

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any service with suspected memory leak |
| Related services | payment-service, realtime-service, api-gateway |
| Environments | prod, staging |
| Use when | Linear memory growth, repeated OOMKill, memory not recovering after GC |
| Do NOT use when | Sudden memory spike (load-induced, not a leak — see [[RB-002-kubernetes-oom-remediation]]) |
| Risk level | Medium |
| Estimated duration | 20–25 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl exec` access to affected pod
- [ ] Profiling tools available in container (jcmd, pprof, heaptrack)
- [ ] Grafana memory dashboard access
- [ ] Disk space to store heap dump (can be 1-4GB)

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl exec` | Pod access for dump capture | Cluster admin |
| `jcmd` / `jmap` (JVM) | Heap dump and GC stats | Pod exec |
| `pprof` (Go) | Heap profile capture | Pod exec/port-forward |
| Eclipse MAT / VisualVM | Heap dump analysis | Local tool |
| Grafana | Memory trend visualization | Read access |

## Trigger

- Memory growing linearly regardless of load (classic leak pattern)
- Repeated OOMKill on regular cadence (e.g., every 12 hours)
- Memory not recovering after GC cycle
- `kubectl top` showing steady upward trend over hours/days

## Triage

1. Confirm linear memory growth (vs. load-induced)
   ```bash
   kubectl top pod <pod> -n <namespace>
   # Run every 5 min — if growing steadily = leak
   ```

2. Check GC effectiveness (JVM)
   ```bash
   kubectl exec <pod> -n <namespace> -- jcmd 1 GC.heap_info
   # What to look for: used after GC progressively increasing = objects not being collected
   ```

3. Check how long until OOM
   ```bash
   # Current memory / growth rate = time to OOM
   # Used: 600MB, Limit: 1GB, Growth: 50MB/hour → OOM in ~8 hours
   ```

## Investigation

1. **JVM: Capture heap dump**
   ```bash
   kubectl exec <pod> -n <namespace> -- jcmd 1 GC.heap_dump /tmp/heap.hprof
   kubectl cp <namespace>/<pod>:/tmp/heap.hprof ./heap-$(date +%s).hprof
   # Analyze with Eclipse MAT: Leak Suspects report
   ```

2. **JVM: Live object histogram (quick check)**
   ```bash
   kubectl exec <pod> -n <namespace> -- jcmd 1 GC.class_histogram | head -20
   # What to look for: unexpected large object counts (millions of same class)
   ```

3. **Go: Capture heap profile**
   ```bash
   kubectl port-forward <pod> -n <namespace> 6060:6060
   curl http://localhost:6060/debug/pprof/heap > heap.prof
   go tool pprof -http=:8080 heap.prof
   ```

4. **Go: Check goroutine count (goroutine leak)**
   ```bash
   curl http://localhost:6060/debug/pprof/goroutine?debug=1 | head -10
   # What to look for: goroutine count in thousands/millions
   ```

5. **Node.js: Capture heap snapshot**
   ```bash
   kubectl exec <pod> -n <namespace> -- kill -USR2 1
   # Check for .heapsnapshot file in working directory
   ```

6. **Decision point:**
   - IF root cause identified → file bug + proceed to Mitigation
   - IF cannot identify from dump → take second dump 10 min later, compare growth

## Mitigation

### Temporary stabilization while fix is developed:

```bash
# Option 1: Increase memory limit (buys time)
kubectl set resources deployment/<name> -n <namespace> --limits=memory=2Gi

# Option 2: Schedule periodic restarts (resets leaked memory)
# Add to deployment: terminationGracePeriodSeconds: 30
# Use a CronJob to restart every 6 hours:
kubectl create job restart-$(date +%s) --from=cronjob/restart-<service> -n <namespace>

# Option 3: If the leak is in a specific feature, disable it via feature flag
```

**After mitigation:** Service should stabilize below 70% limit. File bug with heap dump.

## Verification

- [ ] Memory growth stopped or slowed significantly
- [ ] No OOMKill events in last 2 hours
- [ ] Service responding normally
- [ ] Bug filed with analysis and reproduction steps

```bash
kubectl top pod <pod> -n <namespace>
# Run 3 times over 30 min — should be stable, not growing
```

## Failure Signals

- Memory growing even faster after limit increase (leak accelerating)
- Restarts not helping (leak fills memory in <5 min)
- Cannot capture heap dump (OOM during capture)

## Rollback

1. **Undo memory increase:** Revert to original limit
2. **Undo feature flag change:** Re-enable feature
3. **If restart CronJob causes issues:** Delete the CronJob

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Leak causes OOM every <30 min | Service owner (urgent fix needed) | Direct page | 10 min |
| Cannot capture heap dump | Platform team (profiling tools) | #platform-support | 15 min |
| Leak identified in third-party library | Service owner + vendor support | #data-eng | 30 min |

## Notes

- **Heap dumps are large (often GBs).** Ensure disk space before capturing.
- **Two dumps 10 minutes apart** are more useful than one — diff shows what's growing.
- **Common JVM leak patterns:** unbounded caches, listeners never unregistered, thread-local not cleaned up, static collections growing.
- **Common Go leak patterns:** goroutines blocked on closed channels, unclosed HTTP response bodies, context leaks.
- **Common Node.js leak patterns:** event listener accumulation, closures holding references, undrained streams.
- See [[INC-001-payment-service-oom-crash]] (unbounded cache) and [[INC-058-goroutine-leak-websocket-service]] (goroutine leak).

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Deploy memory-leaking test container in staging, capture dump, verify analysis workflow.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
