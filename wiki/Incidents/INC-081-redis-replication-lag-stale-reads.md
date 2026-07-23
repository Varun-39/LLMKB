---
id: INC-081
title: Redis Replication Lag Causing Stale Session Reads
severity: SEV-2
service: auth-service
environment: prod
category: degradation
date: 2026-04-03
duration: "30m"
tags:
  - incident
  - redis
  - replication
  - stale-reads
  - auth
  - sessions
  - prod
error_family: db-read-replica-lag
resolution_runbook: RB-013
resolution_outcome: resolved
---

## Summary

A burst of writes to the Redis primary during a marketing campaign caused replication lag to spike to 18 seconds on both replicas. Auth-service read traffic (session lookups) was pinned to replicas, returning stale or missing session data and forcing 12,000 users to re-authenticate over a 30-minute window.

## Symptoms

- auth-service logs: `session not found` errors at 800/min (baseline: <5/min)
- Users reporting unexpected logouts across web and mobile
- Redis `INFO replication`: `slave_repl_offset` lag 18 seconds behind primary
- Redis primary `used_memory`: 11.2 GB (max: 12 GB) — near eviction threshold

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~12,000 forced re-authentications |
| Services degraded | auth-service (session reads), all services requiring auth |
| Revenue impact | ~$1.8K estimated abandoned checkouts |
| Duration | 09:15 → 09:45 UTC (30 min) |
| Data loss | None |
| SLA breach | No |
| Customer comms | Status page updated: "Users may need to log in again" |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 09:00 | Marketing email blast triggered 40K concurrent logins |
| 09:10 | Redis write throughput: 48K ops/sec (normal: 8K) |
| 09:15 | Replication lag alert fired (>5s) |
| 09:20 | On-call began investigation |
| 09:30 | Auth-service switched to primary for reads |
| 09:45 | Lag resolved, reads returned to replicas |

## Diagnosis

1. Checked replication lag:
   ```bash
   redis-cli -h redis-primary INFO replication
   # slave0: ip=10.0.1.21,lag=18
   # slave1: ip=10.0.1.22,lag=17
   ```
2. Identified write source — campaign session creation:
   ```bash
   redis-cli -h redis-primary MONITOR | head -100
   # SETEX session:* 3600 <data>  — very high rate
   ```
3. Confirmed replica read routing in auth-service config:
   ```bash
   grep read_from app/config/redis.yaml
   # read_from: replica
   ```

## Resolution

1. **Mitigate:** Switched auth-service session reads to primary
   ```bash
   kubectl set env deployment/auth-service -n auth REDIS_READ_FROM=primary
   kubectl rollout restart deployment/auth-service -n auth
   ```
2. **Fix:** Replication lag cleared naturally as write burst subsided (~10 min)
3. **Restore replicas for reads** once lag < 1 second:
   ```bash
   kubectl set env deployment/auth-service -n auth REDIS_READ_FROM=replica
   kubectl rollout restart deployment/auth-service -n auth
   ```
4. **Verify:**
   ```bash
   redis-cli -h redis-replica-1 INFO replication | grep lag
   # slave_repl_offset lag=0
   ```

## Post-Incident Review

**What went well:**
- Alert fired within 5 minutes of lag onset

**What needs improvement:**
- No automatic fallback from replica to primary on lag threshold
- Campaign load not communicated to SRE team in advance

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Implement read routing failover: auto-promote primary when lag >3s | Backend | 2026-04-17 | Open |
| Pre-event SRE notification for marketing campaigns | Process | 2026-04-10 | Open |
| Add replication lag to on-call runbook | SRE | 2026-04-10 | Open |

## Links

- Runbooks: [[RB-013-redis-memory-management]]
- Related incidents: [[INC-075-redis-sentinel-failover-split-brain]], [[INC-039-redis-maxmemory-eviction-storm]]
