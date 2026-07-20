---
id: INC-083
title: AWS RDS Failover Triggered Connection Storm and App Restart Loop
severity: SEV-1
service: payment-service
environment: prod
category: outage
date: 2026-04-07
duration: "18m"
tags:
  - incident
  - rds
  - aws
  - failover
  - connection-storm
  - payment-service
  - prod
---

## Summary

An AWS RDS multi-AZ failover (triggered by a storage I/O stall on the primary) caused a 45-second database unavailability window. All payment-service instances exhausted their connection pool simultaneously and entered a retry storm, overwhelming the new primary. The connection storm delayed full recovery by 12 additional minutes beyond the RDS failover itself.

## Symptoms

- AWS RDS event: `Multi-AZ failover completed` at 11:22 UTC
- payment-service logs: `connection refused to db-primary` then `too many connections`
- All payment-service pods in `OOMKilled` (connection objects leaked during retry storm)
- `FATAL: remaining connection slots are reserved for non-replication superuser`
- Postgres `max_connections` (200) exhausted by reconnection storm

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~4,500 payment attempts failed |
| Services degraded | payment-service (full outage), api-gateway (payment endpoint 503) |
| Revenue impact | ~$34K in failed transactions |
| Duration | 11:22 → 11:40 UTC (18 min) |
| Data loss | None — no partial transactions committed |
| SLA breach | Yes — payment SLA (99.95%) breached |
| Customer comms | Status page updated at 11:25 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 11:22 | RDS storage I/O stall; failover initiated |
| 11:22 | All payment-service pods lose DB connection |
| 11:23 | Pods begin retry storm (no backoff) |
| 11:25 | New RDS primary online; immediately hit max_connections |
| 11:28 | payment-service pods OOMKilled |
| 11:30 | On-call begins controlled pod restart |
| 11:40 | Service fully recovered |

## Diagnosis

1. Confirmed RDS failover:
   ```bash
   aws rds describe-events --source-type db-instance --duration 60
   # Multi-AZ failover completed for db-payment-prod
   ```
2. Checked connection exhaustion:
   ```bash
   psql -h db-payment-prod.rds.amazonaws.com -U admin -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"
   # idle: 198, active: 2  — all slots consumed by idle connections from retry storm
   ```
3. Confirmed no exponential backoff in payment-service:
   ```bash
   grep reconnect_delay src/db/pool.py
   # reconnect_delay = 0.1  — fixed 100ms, no jitter
   ```

## Resolution

1. **Mitigate:** Killed all idle connections to free slots
   ```bash
   psql -h db-payment-prod -U admin -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='idle' AND application_name='payment-service';"
   ```
2. **Staged pod restart** (10% at a time to avoid another storm):
   ```bash
   kubectl rollout restart deployment/payment-service -n payments
   # Updated max_surge=1, max_unavailable=0 temporarily
   ```
3. **Fix:** Deployed patch with exponential backoff + jitter on DB reconnect
4. **Verify:**
   ```bash
   psql -c "SELECT count(*) FROM pg_stat_activity WHERE application_name='payment-service';"
   # 45 — well within limits
   ```

## Post-Incident Review

**What went well:**
- RDS failover itself was fast (45 seconds); application retry storm was the real incident

**What needs improvement:**
- No exponential backoff on DB reconnection
- Connection pool size not bounded relative to `max_connections`

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Implement exponential backoff with jitter on all DB reconnect paths | Backend | 2026-04-21 | Open |
| Set pool max_size = max_connections / (pod_count * 1.2) | DBA | 2026-04-14 | Open |
| Add pgBouncer in front of RDS to absorb reconnect storms | Platform | 2026-05-01 | Open |

## Links

- Runbooks: [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-009-db-connection-pool-exhausted]], [[INC-064-connection-pool-leak-after-db-failover]]
