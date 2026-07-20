---
id: INC-043
title: gRPC Deadline Exceeded Cascade — Inventory Service Timeout Storm
severity: SEV-2
service: inventory-service
environment: prod
category: degradation
date: 2026-04-08
duration: "22m"
tags:
  - incident
  - grpc
  - timeout
  - cascade
  - latency
  - high
  - prod
---

## Summary

At 15:12 UTC on 2026-04-08, a slow database query in inventory-service caused gRPC responses to exceed the 5-second deadline. Upstream callers (order-service, cart-service) retried aggressively, creating a retry storm that amplified load 8x and drove inventory-service into complete saturation. The cascade affected all checkout operations for 22 minutes.

## Symptoms

- PagerDuty: `InventoryService-HighLatency` at 15:15 UTC
- gRPC error rate: 85% `DEADLINE_EXCEEDED`
- inventory-service CPU: 98% (retry amplification)
- order-service logs: `io.grpc.StatusRuntimeException: DEADLINE_EXCEEDED`
- Checkout success rate: dropped from 99.5% to 12%

## Diagnosis

1. Confirmed deadline exceeded errors
   ```bash
   kubectl logs -l app=inventory-service -n inventory --tail=200 | grep "DEADLINE_EXCEEDED" | wc -l
   # 4,200 in last 60 seconds
   ```

2. Found slow query causing initial latency
   ```bash
   psql -U postgres -d inventory -c "SELECT pid, now()-query_start AS dur, left(query,80) FROM pg_stat_activity WHERE state='active' ORDER BY dur DESC LIMIT 5;"
   # SELECT * FROM stock_levels WHERE warehouse_id IN (...) — 12s (missing index)
   ```

3. Retry amplification confirmed
   ```bash
   kubectl top pods -n inventory
   # Each pod at 980m/1000m CPU — completely saturated from retries
   ```

## Resolution

1. **Mitigate:** Scaled inventory-service to absorb retry load
   ```bash
   kubectl scale deployment/inventory-service -n inventory --replicas=8
   ```

2. **Fix:** Added missing index on `stock_levels(warehouse_id)`
   ```bash
   psql -U postgres -d inventory -c "CREATE INDEX CONCURRENTLY idx_stock_warehouse ON stock_levels(warehouse_id);"
   ```

3. **Verify:** Query time dropped from 12s to 8ms, deadline errors stopped

## Post-Incident Review

- Single slow query amplified 8x by client retries without backoff
- Added exponential backoff with jitter to all gRPC retry policies
- Set `maxRetries: 2` (was unlimited) on order-service and cart-service
- Added circuit breaker: if >50% deadline exceeded in 10s, stop retrying

## Links

- Runbooks: [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-008-db-timeout-auth-db]]
