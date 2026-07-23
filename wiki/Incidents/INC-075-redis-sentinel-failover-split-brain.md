---
id: INC-075
title: Redis Sentinel Split-Brain — Two Masters After Network Heal
severity: SEV-1
service: session-cache
environment: prod
category: outage
date: 2026-06-25
duration: "22m"
tags:
  - incident
  - redis
  - sentinel
  - split-brain
  - failover
  - critical
  - prod
error_family: unknown
resolution_runbook: RB-013
resolution_outcome: resolved
---

## Summary

A 90-second network partition between AZ-a and AZ-b caused Redis Sentinel to promote a replica in AZ-b to master while the original master in AZ-a was still running and accepting writes from local clients. When the partition healed, two masters existed simultaneously. Clients connected to the old master lost 45 seconds of writes when Sentinel forced it to rejoin as a replica (PSYNC full resync discarded the divergent data).

## Symptoms

- PagerDuty: `Redis-SentinelFailover` at 16:20 UTC
- Two Redis instances reporting as master
- Session service: `READONLY You can't write against a read only replica` (some clients)
- After resolution: 450 session keys lost (written to old master during partition)

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~450 users lost session state (forced re-login) |
| Services degraded | session-cache (split-brain), auth-service (session loss) |
| Revenue impact | Minimal — users re-authenticated |
| Duration | 16:20 → 16:42 UTC (22 min) |
| Data loss | 450 session keys (45s of writes to old master) |
| SLA breach | No — within tolerance |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 16:18 | Network partition between AZ-a and AZ-b |
| 16:19:30 | Sentinel quorum in AZ-b declares master down, promotes replica |
| 16:20 | Alert fired: `Redis-SentinelFailover` |
| 16:19-16:20 | Old master in AZ-a still accepting writes from local clients |
| 16:21:30 | Network partition healed |
| 16:22 | Sentinel detects two masters, forces old master to SLAVEOF new master |
| 16:23 | Old master does full PSYNC — discards 45s of divergent writes |
| 16:30 | On-call acknowledged (Dev Patel) |
| 16:35 | Identified 450 lost session keys |
| 16:42 | Affected users re-authenticated, incident closed |

## Diagnosis

1. Confirmed split-brain occurred
   ```bash
   redis-cli -h redis-az-a INFO replication
   # role: master (was master before partition)
   redis-cli -h redis-az-b INFO replication
   # role: master (promoted during partition)
   ```

2. After heal, old master demoted
   ```bash
   redis-cli -h redis-az-a INFO replication
   # role: slave, master_link_status: up (full resync completed, divergent data lost)
   ```

3. Sentinel log showed failover + forced demotion

## Resolution

1. **Mitigate:** Confirmed single master state restored (automatic via Sentinel)

2. **Fix:** Identified lost keys via application-level session miss tracking; users forced to re-authenticate

3. **Verify:** Single master, replication healthy, no more readonly errors

## Post-Incident Review

- Redis Sentinel split-brain is a known limitation during network partitions
- Configured `min-replicas-to-write 1` on master (prevents writes when replicas unreachable)
- Added client-side session fallback: if Redis miss, check DB before forcing re-login
- Evaluating Redis Cluster mode (multi-master with slot ownership) as replacement
- Added alert: if two Redis instances report `role:master` simultaneously

## Links

- Runbooks: [[RB-013-redis-memory-management]]
- Related incidents: [[INC-026-redis-cluster-slot-migration-failure]], [[INC-035-mongodb-election-network-partition]]
