---
id: INC-047
title: Kafka Producer Buffer Full — Order Events Dropped
severity: SEV-1
service: order-service
environment: prod
category: outage
date: 2026-04-25
duration: "19m"
tags:
  - incident
  - kafka
  - producer
  - buffer
  - events
  - critical
  - prod
  - orders
---

## Summary

At 16:45 UTC on 2026-04-25, the order-service Kafka producer began throwing `BufferExhaustedException` after Kafka broker-2 went offline for a planned maintenance that was not communicated to the application team. With one of three brokers down and partition leaders being reassigned, producer latency spiked to 30s. The 32MB producer buffer filled within 90 seconds, and all subsequent order events were dropped (producer configured with `block.on.buffer.full=false`). 2,400 order events were lost.

## Symptoms

- PagerDuty: `OrderService-KafkaProducerErrors` at 16:47 UTC
- order-service logs: `org.apache.kafka.common.errors.BufferExhaustedException`
- Kafka consumer lag: flatlined (no new messages arriving)
- Order confirmation emails not sending (downstream of Kafka)
- order-service error rate: 0% (HTTP responses succeeded, events silently dropped)

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~2,400 orders placed without event processing |
| Services degraded | order-service events, notification-service, analytics pipeline |
| Revenue impact | None directly — orders placed successfully, but confirmations delayed |
| Duration | 16:45 → 17:04 UTC (19 min) |
| Data loss | 2,400 order events dropped (recovered from DB replay) |
| SLA breach | Yes — event delivery SLA breached |
| Customer comms | 2,400 order confirmation emails delayed by 45 min |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 16:40 | Kafka broker-2 taken offline for maintenance (planned, not communicated) |
| 16:42 | Partition leader reassignment began |
| 16:45 | Producer buffer full, events begin dropping |
| 16:47 | Alert fired: `OrderService-KafkaProducerErrors` |
| 16:49 | On-call acknowledged (Liam Chen) |
| 16:55 | Kafka broker maintenance identified as trigger |
| 16:58 | broker-2 brought back online early |
| 17:02 | Partition leaders rebalanced, producer recovered |
| 17:04 | DB replay job triggered for missed events |

## Diagnosis

1. Confirmed producer buffer exhaustion
   ```bash
   kubectl logs -l app=order-service -n orders --tail=100 | grep BufferExhausted
   # 2,400 occurrences in 19 minutes
   ```

2. Checked Kafka cluster state
   ```bash
   kafka-broker-api-versions.sh --bootstrap-server kafka:9092
   # broker-2: connection refused
   ```

3. Confirmed planned maintenance on broker-2 (ops calendar)

## Resolution

1. **Mitigate:** Requested broker-2 brought back online early
2. **Fix:** Ran DB replay job to re-emit missed order events
   ```bash
   kubectl create job order-replay --from=cronjob/order-event-replay -n orders
   ```
3. **Verify:** Consumer lag cleared, all 2,400 events processed

## Post-Incident Review

- Producer configured to silently drop events on buffer full
- Changed to `block.on.buffer.full=true` with `max.block.ms=60000` (block up to 60s before failing)
- Added maintenance communication requirement to Kafka ops procedures
- Added Kafka consumer lag alert: if lag increases >1000 in 5 min, page immediately

## Links

- Runbooks: [[RB-014-kafka-cluster-operations]]
- Related incidents: [[INC-023-kafka-consumer-rebalance-storm]]
