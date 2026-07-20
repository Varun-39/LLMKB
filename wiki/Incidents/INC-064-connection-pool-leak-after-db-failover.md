---
id: INC-064
title: HikariCP Connection Pool Leak After Database Failover
severity: SEV-2
service: order-service
environment: prod
category: degradation
date: 2026-06-07
duration: "28m"
tags:
  - incident
  - hikaricp
  - connection-pool
  - database
  - failover
  - java
  - high
  - prod
---

## Summary

After a planned RDS failover at 02:00 UTC on 2026-06-07, HikariCP in order-service did not properly invalidate broken connections in the pool. The pool's `maxLifetime` was set to 30 minutes, meaning stale connections to the old primary lingered. For 28 minutes, 60% of checkout requests failed because they picked up a broken connection, got `Connection is closed`, and the request failed without retry.

## Symptoms

- order-service logs: `Connection is not available, request timed out after 30000ms`
- HikariCP metrics: `hikaricp_connections_active` = 20, `hikaricp_connections_idle` = 0
- Checkout error rate: 60% (random — depends on which connection pulled from pool)
- RDS: failover completed at 02:00:45, new primary healthy

## Diagnosis

1. Confirmed stale connections
   ```bash
   kubectl logs -l app=order-service -n orders --tail=100 | grep -c "Connection is closed"
   # 450 in last 5 minutes
   ```

2. HikariCP validation query not configured
   ```bash
   kubectl exec order-service-xyz -n orders -- env | grep HIKARI
   # HIKARI_CONNECTION_TEST_QUERY not set
   # HIKARI_MAX_LIFETIME=1800000 (30 min)
   ```

3. Connections created before failover still in pool (valid TCP socket, but server-side closed)

## Resolution

1. **Mitigate:** Restart pods to flush connection pool
   ```bash
   kubectl rollout restart deployment/order-service -n orders
   ```

2. **Fix:** Added `connectionTestQuery=SELECT 1` and reduced `maxLifetime` to 5 minutes

3. **Verify:** No more stale connection errors after subsequent failover test

## Post-Incident Review

- HikariCP without validation query cannot detect server-side connection closure
- Added `connectionTestQuery` to all JVM services
- Reduced `maxLifetime` from 30 min to 5 min
- Added connection validation on checkout from pool (`testOnBorrow` equivalent)

## Links

- Runbooks: [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-053-dns-ttl-cached-stale-endpoint]]
