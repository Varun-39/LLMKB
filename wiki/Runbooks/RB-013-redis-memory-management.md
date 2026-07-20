---
id: RB-013
title: Redis Memory Management and Eviction Recovery
service: redis
related_services:
  - auth-service
  - session-cache
  - user-service
severity: SEV-2
environment: prod
category: resource-exhaustion
risk_level: medium
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - redis
  - memory
  - eviction
  - cache
  - prod
related_incidents:
  - "[[INC-039-redis-maxmemory-eviction-storm]]"
  - "[[INC-026-redis-cluster-slot-migration-failure]]"
  - "[[INC-075-redis-sentinel-failover-split-brain]]"
related_runbooks:
  - "[[RB-002-kubernetes-oom-remediation]]"
related_guardrails: []
---

## Purpose

Diagnose and resolve Redis memory pressure including eviction storms, maxmemory saturation, and memory fragmentation.

**Desired outcome:** Redis memory usage below 70% of maxmemory, eviction rate at 0, cache hit rate at baseline.

## Success Criteria

- `INFO memory` shows `used_memory` < 70% of `maxmemory`
- `evicted_keys` counter stable (not incrementing)
- Cache hit rate returned to baseline (>95% for session cache)
- No `OOM command not allowed` errors in client logs
- Memory fragmentation ratio < 1.5

## Scope

| Attribute | Value |
|-----------|-------|
| Service | redis |
| Related services | auth-service, session-cache, user-service |
| Environments | prod, staging |
| Use when | `*-RedisEvictionHigh`, `*-RedisMemoryHigh`, or `OOM command not allowed` errors |
| Do NOT use when | Redis is unreachable (network issue, not memory) |
| Risk level | Medium |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] `redis-cli` access to affected instance
- [ ] Knowledge of which applications use this Redis instance
- [ ] Grafana access to Redis dashboards

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `redis-cli` | Redis diagnostics and configuration | Admin access |
| Grafana | Memory trend and eviction metrics | Read access |
| `kubectl` | Application-side operations | Cluster admin |

## Trigger

- Alert: `*-RedisEvictionHigh` (evicted_keys increasing)
- Alert: `*-RedisMemoryHigh` (>85% of maxmemory)
- Symptom: Application logs `OOM command not allowed when used memory > maxmemory`
- Symptom: Cache miss rate spike correlating with evictions

## Triage

1. Check Redis memory state
   ```bash
   redis-cli -h <host> INFO memory
   # What to look for: used_memory_human vs maxmemory_human, mem_fragmentation_ratio
   ```

2. Check eviction rate
   ```bash
   redis-cli -h <host> INFO stats | grep evicted_keys
   # Run twice with 10s gap to see rate
   ```

3. Check eviction policy
   ```bash
   redis-cli -h <host> CONFIG GET maxmemory-policy
   # allkeys-lru, volatile-lru, noeviction, etc.
   ```

## Investigation

1. **Find large keys consuming memory**
   ```bash
   redis-cli -h <host> --bigkeys
   # What to look for: unexpectedly large keys, new key patterns
   ```

2. **Check key count by pattern**
   ```bash
   redis-cli -h <host> DBSIZE
   redis-cli -h <host> --scan --pattern "session:*" | wc -l
   redis-cli -h <host> --scan --pattern "cache:*" | wc -l
   # Compare with expected counts
   ```

3. **Check memory breakdown**
   ```bash
   redis-cli -h <host> MEMORY STATS
   # What to look for: dataset.percentage, overhead.total
   ```

4. **Identify new key patterns (not previously present)**
   ```bash
   redis-cli -h <host> --scan --pattern "*" | head -1000 | cut -d: -f1-2 | sort | uniq -c | sort -rn | head -10
   ```

5. **Decision point:**
   - IF new large key pattern identified → proceed to Mitigation Option A
   - IF general growth beyond capacity → proceed to Mitigation Option B
   - IF fragmentation issue → proceed to Mitigation Option C
   - IF eviction policy wrong → proceed to Mitigation Option D

## Mitigation

### Option A: Remove unexpected large keys

```bash
# Delete keys matching the problematic pattern:
redis-cli -h <host> --scan --pattern "user:prefs:*" | xargs redis-cli -h <host> DEL
# Or set TTL on existing keys:
redis-cli -h <host> --scan --pattern "user:prefs:*" | xargs -I {} redis-cli -h <host> EXPIRE {} 3600
```

### Option B: Increase maxmemory

```bash
redis-cli -h <host> CONFIG SET maxmemory 6gb
# Persist across restarts:
redis-cli -h <host> CONFIG REWRITE
```

### Option C: Fix memory fragmentation (restart)

```bash
# Redis 4+: online defrag
redis-cli -h <host> CONFIG SET activedefrag yes
# If ratio >2.0, restart may be needed:
kubectl rollout restart statefulset/redis -n cache
```

### Option D: Change eviction policy

```bash
redis-cli -h <host> CONFIG SET maxmemory-policy allkeys-lru
redis-cli -h <host> CONFIG REWRITE
```

**After mitigation:** Monitor for 10 minutes — eviction rate at 0, memory stable.

## Verification

- [ ] `used_memory` < 70% of `maxmemory`
- [ ] `evicted_keys` not incrementing
- [ ] Cache hit rate at baseline
- [ ] No OOM errors in application logs
- [ ] Memory fragmentation ratio < 1.5

```bash
redis-cli -h <host> INFO memory | grep -E "used_memory_human|maxmemory_human|mem_fragmentation_ratio"
redis-cli -h <host> INFO stats | grep evicted_keys
```

## Failure Signals

- Memory grows back to maxmemory within minutes
- Eviction rate remains high after increase
- Application still logging OOM errors
- Cache miss rate not recovering

**If any failure signal is present:** Escalate.

## Rollback

1. **Undo maxmemory increase:** `redis-cli CONFIG SET maxmemory <original>`
2. **Undo eviction policy change:** `redis-cli CONFIG SET maxmemory-policy <original>`
3. **If wrong keys deleted:** No undo — they must be rebuilt by the application.

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Memory growth continues uncontrolled | Service owner (leaking app) | Direct page | 10 min |
| Need to increase beyond node capacity | Platform team | #platform-support | 15 min |
| Redis cluster migration needed | Data platform team | #data-eng | 30 min |
| Session data loss affecting users | EM + on-call | #incident-response | 5 min |

## Notes

- **`noeviction` policy** causes OOM errors returned to clients. Most prod services should use `allkeys-lru`.
- **Fragmentation ratio >2.0** means Redis is using 2x the actual data size in RSS. Restart fixes this.
- **New cache consumers must be capacity-planned.** See [[INC-039-redis-maxmemory-eviction-storm]] where a new feature consumed shared capacity.
- **Redis MEMORY USAGE <key>** gives exact bytes for a specific key.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Fill staging Redis to 90% maxmemory, verify eviction behavior and alerting.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
