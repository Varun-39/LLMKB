---
id: INC-097
title: Celery Worker Task Queue Buildup Due to Prefetch Misconfiguration
severity: SEV-2
service: reporting-service
environment: prod
category: degradation
date: 2026-05-05
duration: "1h 30m"
tags:
  - incident
  - celery
  - task-queue
  - prefetch
  - reporting-service
  - redis
  - prod
---

## Summary

The reporting-service Celery workers had `worker_prefetch_multiplier=100` (default), meaning each of 4 workers reserved 100 tasks from the queue at startup. A new long-running report task (avg 90 seconds) caused all 400 prefetched tasks to be held by workers that could only process them serially, while 2,800 new short tasks (avg 2s) sat in the queue starved for 90 minutes.

## Symptoms

- reporting-service: short report requests timing out after 5 minutes
- Celery queue depth: `celery-short` queue at 2,800 tasks (normal: <50)
- Workers busy: all 4 workers processing long-running tasks from prefetch buffer
- Users: "Quick reports take forever, but large reports finish instantly"

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~1,400 users waiting on quick reports |
| Services degraded | reporting-service (short report queue starved) |
| Revenue impact | N/A |
| Duration | 09:00 → 10:30 UTC (1h 30m) |
| Data loss | None |
| SLA breach | Yes — report delivery SLA (5 min) breached for 1,400 tasks |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 08:45 | New long-running report type deployed |
| 09:00 | Long tasks prefetched by all workers |
| 09:05 | Short task queue begins building |
| 09:30 | 5-minute timeout alert fires on short reports |
| 09:45 | On-call begins investigation |
| 10:00 | Prefetch multiplier identified as cause |
| 10:30 | Workers restarted with `prefetch_multiplier=1`; queue drained |

## Diagnosis

1. Checked queue depth via Redis:
   ```bash
   redis-cli llen celery
   # 2847
   redis-cli llen celery-long
   # 0
   ```
2. Confirmed workers are all busy with long tasks:
   ```bash
   celery -A reporting inspect active
   # worker-1: [{name: generate_full_report, started: 09:02}]
   # worker-2: [{name: generate_full_report, started: 09:03}]
   # (all 4 workers on long tasks)
   ```
3. Checked Celery config:
   ```bash
   grep prefetch reporting/celery_config.py
   # worker_prefetch_multiplier = 100  (default never overridden)
   ```

## Resolution

1. **Mitigated** by restarting workers with reduced prefetch:
   ```bash
   kubectl set env deployment/celery-worker -n reporting CELERYD_PREFETCH_MULTIPLIER=1
   kubectl rollout restart deployment/celery-worker -n reporting
   ```
2. Workers picked up short tasks; queue drained in ~25 minutes
3. **Fix:** Separated long and short tasks onto dedicated queues with dedicated workers:
   ```bash
   # Short tasks worker:
   celery worker -Q celery-short --prefetch-multiplier=4 --concurrency=8
   # Long tasks worker:
   celery worker -Q celery-long --prefetch-multiplier=1 --concurrency=2
   ```

## Post-Incident Review

**What went well:**
- Celery inspect commands gave clear visibility into what workers were doing

**What needs improvement:**
- Single queue for all task types with no priority separation
- Default `prefetch_multiplier=100` is dangerous for mixed workloads

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Separate long and short task queues with dedicated workers | Backend | 2026-05-12 | Open |
| Set `prefetch_multiplier=1` as org default for all Celery workers | Backend | 2026-05-12 | Open |
| Add alert: Celery queue depth > 500 per queue | Observability | 2026-05-12 | Open |

## Links

- Runbooks: [[RB-021-cronjob-failure-investigation]]
- Related incidents: [[INC-023-kafka-consumer-rebalance-storm]], [[INC-040-cronjob-thundering-herd-db]]
