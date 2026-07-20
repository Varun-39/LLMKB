---
id: INC-014
title: Node DiskPressure — Container Logs Filling Ephemeral Storage
severity: SEV-2
service: api-gateway
environment: prod
category: degradation
date: 2026-03-27
duration: "36m"
detection_gap: "2m"
tags:
  - incident
  - kubernetes
  - disk
  - node
  - ephemeral-storage
  - high
  - prod
  - api
---

## Summary

Node `ip-10-0-2-91` entered `DiskPressure` condition at 11:08 UTC on 2026-03-27, triggering eviction of low-priority pods and causing 3 api-gateway pods to be evicted and rescheduled. The node's 50 GB ephemeral storage partition was exhausted by unrotated container logs from a verbose api-gateway debug build that had been running for 72 hours after a developer accidentally merged a debug logging branch to main.

## Symptoms

- PagerDuty: `K8s-NodeDiskPressure` at 11:10 UTC
- `kubectl get nodes` — `ip-10-0-2-91` tainted with `node.kubernetes.io/disk-pressure`
- 3 api-gateway pods evicted: `The node had condition: DiskPressure`
- P99 API latency: 190 ms → 1.4 s (under-replicated pods absorbing load)
- `df -h` on node: `/dev/xvda1 50G 50G 0 100%`
- Container log directory consuming 44 GB on that node

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~2,800 API users during degraded window |
| Services degraded | api-gateway (3/6 pods evicted and rescheduling) |
| Revenue impact | ~$6K in degraded/failed requests |
| Duration | 11:08 → 11:44 UTC (36 min) |
| Data loss | None |
| SLA breach | No — degradation stayed within SLA threshold |
| Customer comms | N/A — partial degradation, no status page update |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 11:08 | Node entered DiskPressure condition |
| 11:10 | Alert fired: `K8s-NodeDiskPressure` |
| 11:11 | On-call acknowledged (Marcus Webb) |
| 11:15 | SSH to node; identified 44 GB container log directory |
| 11:20 | Debug build image (v4.0.9-debug) identified as culprit |
| 11:25 | Container log truncated, disk freed to 8G used |
| 11:27 | Node exited DiskPressure; taint removed |
| 11:35 | Redeployed api-gateway with correct production image (v4.0.9) |
| 11:44 | All pods healthy, latency normalized, incident closed |

## Diagnosis

1. Confirmed DiskPressure condition and taint
   ```bash
   kubectl describe node ip-10-0-2-91 | grep -A5 "Conditions"
   # DiskPressure: True — kubelet has disk pressure
   kubectl describe node ip-10-0-2-91 | grep Taints
   # node.kubernetes.io/disk-pressure:NoSchedule
   ```

2. SSH to node and identified disk consumers
   ```bash
   ssh ec2-user@10.0.2.91
   df -h /
   # /dev/xvda1 50G 50G 0 100%
   du -sh /var/lib/docker/containers/* | sort -rh | head -5
   # 42G   /var/lib/docker/containers/a8f3c.../
   ```

3. Identified the verbose container
   ```bash
   docker inspect a8f3c... | grep "Name"
   # api-gateway-6d4f-xr92
   docker logs --tail=5 a8f3c...
   # All DEBUG level log lines — every request fully traced
   ```

4. Confirmed api-gateway image tag running
   ```bash
   kubectl get pod api-gateway-6d4f-xr92 -n gateway \
     -o jsonpath='{.spec.containers[0].image}'
   # registry.internal/api-gateway:v4.0.9-debug  ← debug build
   ```

5. Traced to Git commit — debug branch accidentally merged to main 72 hours prior

## Resolution

1. **Mitigate:** Cleared container log directory to immediately free disk
   ```bash
   truncate -s 0 /var/lib/docker/containers/a8f3c.../*-json.log
   # Disk freed: 50G → 8G used
   ```

2. **Fix:** Redeployed api-gateway with correct production image (v4.0.9)
   ```bash
   kubectl set image deployment/api-gateway -n gateway \
     api-gateway=registry.internal/api-gateway:v4.0.9
   kubectl rollout restart deployment/api-gateway -n gateway
   ```

3. **Verify:** Node exited DiskPressure and all pods healthy
   ```bash
   kubectl get nodes  # ip-10-0-2-91 Ready, no taint
   kubectl get pods -n gateway -l app=api-gateway  # All 6 Running
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| DiskPressure causing pod evictions | Escalate to platform team | #platform-support |
| >2 nodes in DiskPressure simultaneously | Page EM, assess cluster-wide impact | #incident-response |
| Unable to clear disk within 10 min | Engage infra for node replacement | #platform-support |

## Post-Incident Review

**What went well:**
- Node DiskPressure alert fired promptly
- Disk cleared non-destructively by truncating log files

**What needs improvement:**
- Debug build tag deployed to prod with no gate — image naming did not distinguish debug from release
- No ephemeral-storage resource limits on any pods
- No container log size limits in Docker daemon config

**Contributing factors (beyond root cause):**
- Debug branch accidentally merged to main; no CI gate blocking `-debug` images in prod
- No `ephemeral-storage` limits on pod specs
- Docker daemon not configured with `max-size` and `max-file` log options

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Deploy correct production image, clear disk | Marcus Webb | 2026-03-27 | Done |
| Add image tag policy: block `*-debug` images from reaching prod registry | Platform team | 2026-04-10 | Open |
| Set `ephemeral-storage` limits on all pod specs (500 MB default) | Platform team | 2026-04-10 | Open |
| Configure Docker daemon: `"log-opts": {"max-size": "100m", "max-file": "3"}` | SRE team | 2026-04-10 | Open |
| Add alert: node ephemeral storage >70% | SRE team | 2026-04-10 | Open |

## Links

- Runbooks: [[RB-003-disk-space-full]], [[RB-007-pod-crash-investigation]]
- Related incidents: [[INC-005-disk-full-logs-node01]], [[INC-004-k8s-node-notready]]
- PR/commit: N/A
- Post-mortem doc: N/A
