---
id: INC-023
title: Kafka Consumer Group Rebalance Storm
severity: SEV-2
service: order-processing
environment: prod
category: degradation
date: 2026-01-22
duration: "1h15m"
tags:
  - incident
  - kafka
  - messaging
  - consumer-group
  - rebalance
  - prod
---

## Summary

The `order-processing` consumer group entered a continuous rebalance loop after a rolling deployment increased consumer instances from 6 to 12 without adjusting `session.timeout.ms`. Consumers repeatedly joined and left the group, causing message processing to stall for 75 minutes. ~45,000 orders were delayed.

## Symptoms

- Consumer lag on `orders-topic` spiked from 200 to 890,000 in 15 minutes
- Application logs: `org.apache.kafka.clients.consumer.CommitFailedException: Commit cannot be completed since the group has already rebalanced`
- Grafana: consumer group state flipping between `PreparingRebalance` and `CompletingRebalance` every 8-12 seconds
- PagerDuty: `Kafka-ConsumerLag-Critical` at 14:22 UTC
- No messages being committed — offset unchanged for 20+ minutes

## Diagnosis

1. Checked consumer group state:
   ```bash
   kafka-consumer-groups.sh --bootstrap-server kafka-01:9092 --describe --group order-processing
   # STATE: PreparingRebalance
   ```
2. Noticed 12 consumers joining/leaving repeatedly in broker logs
3. Root cause: `session.timeout.ms=10000` (default) was too low for 12 consumers. Rebalance took ~12s, exceeding session timeout, causing members to be kicked and re-triggering rebalance
4. The rolling deploy added 6 new consumers simultaneously, each triggering a new rebalance before the previous completed

## Resolution

1. Scaled deployment back to 6 replicas to stop the storm:
   ```bash
   kubectl scale deployment order-processor --replicas=6
   ```
2. Waited for group to stabilize (single successful rebalance)
3. Updated consumer config:
   ```properties
   session.timeout.ms=45000
   max.poll.interval.ms=300000
   partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
   ```
4. Gradually scaled back to 12 replicas (2 at a time, 5-minute intervals)
5. Confirmed zero rebalances during scale-up with cooperative assignor

## Post-Incident Review

- Default `session.timeout.ms` is too aggressive for large consumer groups
- Switched to CooperativeStickyAssignor to avoid stop-the-world rebalances
- Added pre-deployment check: consumer count changes must be gradual
- Alert added: if >3 rebalances per 5 minutes, page on-call

## Links

- Related: [[RB-010-kafka-consumer-lag-remediation]]
- Related: [[RB-014-kafka-cluster-operations]]
