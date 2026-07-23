---
id: INC-039
title: Redis Maxmemory Eviction Storm — Session Cache Miss Spike
severity: SEV-2
service: auth-service
environment: prod
category: degradation
date: 2026-03-18
duration: "25m"
detection_gap: "3m"
tags:
  - incident
  - redis
  - cache
  - eviction
  - memory
  - auth
  - high
  - prod
error_family: unknown
resolution_runbook: RB-013
resolution_outcome: resolved
---

## Summary

At 14:30 UTC on 2026-03-18, the shared Redis instance used for session caching hit its `maxmemory` limit (4GB). The `allkeys-lru` eviction policy began aggressively evicting session tokens, causing a 40% cache miss rate. auth-service experienced a 5x increase in latency as every evicted session required a full database lookup and token revalidation. Users experienced intermittent logouts and slow page loads.

## Symptoms

- PagerDuty: `Redis-EvictionRateHigh` at 14:33 UTC
- Redis INFO: `evicted_keys` climbing at 2,000/sec
- auth-service metrics: cache miss rate jumped from 2% to 40%
- auth-service P99 latency: 180ms → 950ms
- User reports: intermittent logouts and "session expired" errors

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~6,000 users experienced session interruptions |
| Services degraded | auth-service (slow), all downstream services (auth latency) |
| Revenue impact | Minimal — sessions eventually recovered |
| Duration | 14:30 → 14:55 UTC (25 min) |
| Data loss | None — sessions recreated on next login |
| SLA breach | No — degradation within SLA tolerance |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 14:30 | Redis hit 4GB maxmemory, evictions began |
| 14:33 | Alert fired: `Redis-EvictionRateHigh` |
| 14:35 | On-call acknowledged (Chen Wei) |
| 14:40 | Root cause identified — new feature storing large JSON blobs in Redis |
| 14:45 | maxmemory increased to 6GB temporarily |
| 14:48 | Eviction rate dropped to 0 |
| 14:55 | Cache miss rate back to baseline, incident closed |

## Diagnosis

1. Confirmed Redis memory at limit
   ```bash
   redis-cli -h redis-prod.internal INFO memory
   # used_memory_human: 4.00G, maxmemory_human: 4.00G
   # evicted_keys: 142000 (last 5 min)
   ```

2. Identified memory growth source
   ```bash
   redis-cli -h redis-prod.internal --bigkeys
   # Largest string: user:prefs:* keys averaging 45KB each (new feature)
   # Previous session keys: ~500 bytes each
   ```

3. Correlated with recent deployment — v3.8.0 of user-preferences-service began caching full preference JSON in Redis 2 days ago

## Resolution

1. **Mitigate:** Increased maxmemory to 6GB
   ```bash
   redis-cli -h redis-prod.internal CONFIG SET maxmemory 6gb
   ```

2. **Fix:** Moved user preference caching to a separate Redis instance with its own memory budget

3. **Verify:** Eviction rate at 0, cache miss rate at 2%
   ```bash
   redis-cli -h redis-prod.internal INFO stats | grep evicted_keys
   # evicted_keys stable (no new evictions)
   ```

## Post-Incident Review

- New feature consumed shared Redis capacity without capacity planning
- Added per-keyspace memory tracking with alerts at 70% of maxmemory
- Established rule: new cache consumers must request separate namespace or instance
- Added Redis memory forecasting to deployment checklist

## Links

- Runbooks: [[RB-013-redis-memory-management]]
- Related incidents: [[INC-026-redis-cluster-slot-migration-failure]]
