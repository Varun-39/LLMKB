---
id: RB-036
title: Redis Replication Lag Recovery and Read Routing Failover
service: auth-service
related_services:
  - payment-service
  - frontend
severity: SEV-2
environment: prod
category: performance
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - redis
  - replication
  - lag
  - failover
  - auth-service
  - prod
---

## Purpose

Recover from Redis replication lag causing stale or missing reads by temporarily routing reads to the primary and restoring replica reads once lag clears.

**Desired outcome:** Read latency back to baseline, replication lag < 1 second, no stale session reads.

## Success Criteria

- Redis `INFO replication` shows slave lag = 0 on all replicas
- Application error rate (session-not-found, stale-reads) back to baseline
- No active alerts for replication lag
- Read traffic restored to replicas without recurring lag

## Scope

| Attribute | Value |
|-----------|-------|
| Service | auth-service (primary), any service using Redis with replica reads |
| Related services | payment-service, frontend |
| Environments | prod |
| Use when | `RedisReplicationLag > 5s` alert fires, stale read errors spike |
| Do NOT use when | Redis cluster is completely down (see RB-013) |
| Risk level | Medium — switching reads to primary increases primary load |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] `redis-cli` access to primary and replicas
- [ ] `kubectl` access to affected namespace
- [ ] Know which services are configured to read from replicas

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `redis-cli` | Inspect replication state | Read access |
| `kubectl` | Update service env vars | Namespace admin |
| Grafana | Monitor lag and error rate | Read access |

## Trigger

- Alert: `RedisReplicationLag > 5s` for > 2 minutes
- Symptom: Users reporting unexpected logouts or stale data
- Log pattern: `session not found` errors spiking in service logs

## Triage

1. Confirm lag is on replica, not a network blip:
   ```bash
   redis-cli -h redis-primary INFO replication | grep -E "slave|lag"
   # slave0: ip=10.0.1.21,lag=18  — confirmed
   ```
2. Check if primary is under write pressure:
   ```bash
   redis-cli -h redis-primary INFO stats | grep instantaneous_ops_per_sec
   # instantaneous_ops_per_sec: 48000  — high
   ```
3. If lag < 3s and decreasing → watch for 5 minutes before acting.

## Investigation

1. **Identify write source causing the lag**
   ```bash
   redis-cli -h redis-primary MONITOR | head -200
   # What to look for: high-rate SETEX/SET commands from a single service
   ```
2. **Check replica connection status**
   ```bash
   redis-cli -h redis-primary INFO replication
   # master_repl_offset vs slave_repl_offset — gap = lag bytes
   ```
3. **Check if replica is healthy (not crashed)**
   ```bash
   redis-cli -h redis-replica-1 PING
   # Expected: PONG
   ```
4. **Decision point:**
   - IF replica is healthy but lagging due to write burst → Option A (reroute reads)
   - IF replica is disconnected or crashed → Option B (restart replica)
   - IF primary memory near limit → Option C (reduce write volume)

## Mitigation

### Option A: Route reads to primary temporarily

```bash
# Update service env var to read from primary
kubectl set env deployment/<service> -n <namespace> REDIS_READ_FROM=primary
kubectl rollout restart deployment/<service> -n <namespace>
# Monitor: lag should clear naturally as write burst subsides
```

### Option B: Restart lagging replica

```bash
redis-cli -h redis-replica-1 DEBUG SLEEP 0  # wake if sleeping
# OR restart the pod:
kubectl rollout restart statefulset/redis-replica -n redis
# Replica will resync from primary — may take 1-5 min for large datasets
```

### Option C: Throttle write source

```bash
# Identify and temporarily rate-limit the high-write service
kubectl scale deployment/<write-heavy-service> -n <namespace> --replicas=1
# Or set Redis write rate limit (use carefully):
redis-cli -h redis-primary CONFIG SET hz 10
```

**After mitigation:** Monitor lag every 2 minutes. Do not restore replica reads until lag = 0.

## Verification

- [ ] `redis-cli -h redis-primary INFO replication` shows lag = 0 on all slaves
- [ ] Service error rate (stale reads, session errors) back to baseline
- [ ] No active replication lag alerts

```bash
redis-cli -h redis-replica-1 INFO replication | grep lag
# Expected: lag=0
```

## Failure Signals

- Lag not decreasing after 10 minutes even with reads on primary
- Replica disconnecting repeatedly (check replica logs)
- Primary CPU > 90% after routing reads to it

## Rollback

1. **Restore reads to replica** once lag cleared:
   ```bash
   kubectl set env deployment/<service> -n <namespace> REDIS_READ_FROM=replica
   kubectl rollout restart deployment/<service> -n <namespace>
   ```
2. If primary overloaded due to added read traffic → scale up primary instance before restoring.

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Lag > 60s and not decreasing | Redis/Platform team | #platform-support | 10 min |
| Replica refuses to reconnect | Redis specialist | #data-eng | 10 min |
| Primary at memory limit | DBA + SRE | #incident-response | Immediate |

## Notes

- Campaign or batch events are the most common cause of write bursts — check with product team before incident.
- Routing reads to primary doubles primary memory pressure; don't leave it in this state long.
- See [[INC-081-redis-replication-lag-stale-reads]] for a real example.

## Maintenance

- **Last tested:** 2026-05-11
- **Review cycle:** Quarterly
- **Next review:** 2026-08-11
- **Test method:** Simulate write burst in staging and validate failover procedure.

## last Updated

| Date | Author | Change |
|------|--------|--------|
| 2026-05-11 | SRE Team | Initial publication |
