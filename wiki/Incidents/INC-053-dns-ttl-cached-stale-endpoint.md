---
id: INC-053
title: DNS TTL Caching Stale Endpoint After RDS Failover
severity: SEV-1
service: payment-service
environment: prod
category: outage
date: 2026-05-12
duration: "22m"
tags:
  - incident
  - dns
  - rds
  - failover
  - caching
  - database
  - critical
  - prod
error_family: unknown
resolution_runbook: RB-005
resolution_outcome: resolved
---

## Summary

At 03:15 UTC on 2026-05-12, an RDS Multi-AZ failover completed in 35 seconds, but payment-service continued connecting to the old primary IP for 22 minutes. The JVM's built-in DNS caching (`networkaddress.cache.ttl=300`) held the stale A record, causing all database connections to fail with `Connection refused` until the cache expired or pods were restarted.

## Symptoms

- PagerDuty: `PaymentService-DBConnectionFailed` at 03:16 UTC
- payment-service logs: `Connection refused to 10.0.1.45:5432` (old primary IP)
- RDS console: failover completed at 03:15:35 UTC, new primary at 10.0.2.88
- Other services (Python, Go): recovered within 30 seconds (no DNS caching)
- Only JVM services affected

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~3,200 users attempting payments |
| Services degraded | payment-service, order-service (JVM-based) |
| Revenue impact | ~$18K in failed transactions |
| Duration | 03:15 → 03:37 UTC (22 min) |
| Data loss | None — transactions failed cleanly |
| SLA breach | Yes — payments SLA breached |
| Customer comms | Status page updated at 03:20 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 03:15 | RDS Multi-AZ failover triggered (storage issue on primary) |
| 03:15:35 | Failover complete, new primary IP: 10.0.2.88 |
| 03:16 | Alert fired: `PaymentService-DBConnectionFailed` |
| 03:18 | On-call acknowledged (Sofia Andersson) |
| 03:25 | JVM DNS caching identified as cause |
| 03:28 | Rolled restart of payment-service pods |
| 03:32 | All pods restarted, connecting to new primary |
| 03:37 | Error rate at baseline, incident closed |

## Diagnosis

1. Confirmed DB connection failure
   ```bash
   kubectl logs -l app=payment-service -n payments --tail=50 | grep "Connection refused"
   # Connection refused to 10.0.1.45:5432 (old IP)
   ```

2. Checked RDS endpoint resolution
   ```bash
   nslookup payment-db.cluster-abc.us-east-1.rds.amazonaws.com
   # 10.0.2.88 (new IP — DNS already updated)
   ```

3. JVM resolving stale IP due to internal cache
   ```bash
   kubectl exec payment-service-xyz -n payments -- \
     java -XshowSettings:all 2>&1 | grep networkaddress
   # networkaddress.cache.ttl=300 (5 minutes)
   ```

## Resolution

1. **Mitigate:** Rolling restart to flush JVM DNS cache
   ```bash
   kubectl rollout restart deployment/payment-service -n payments
   ```

2. **Fix:** Set JVM DNS TTL to 5 seconds for all JVM services
   ```bash
   # Added to JVM_OPTS: -Dnetworkaddress.cache.ttl=5
   ```

3. **Verify:** Connections to new primary working

## Post-Incident Review

- JVM DNS caching is a known issue with RDS failovers but was never addressed
- Set `networkaddress.cache.ttl=5` across all JVM services
- Added HikariCP connection validation: `SELECT 1` before each use
- Added alert: if DB connection errors >0 for 30 seconds post-failover, auto-restart pods

## Links

- Runbooks: [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-008-db-timeout-auth-db]], [[INC-022-dns-nxdomain-coredns-cache]]
