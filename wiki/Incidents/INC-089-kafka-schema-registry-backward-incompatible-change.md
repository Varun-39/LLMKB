---
id: INC-089
title: Kafka Schema Registry Backward Incompatible Change Broke Consumers
severity: SEV-2
service: payment-service
environment: prod
category: degradation
date: 2026-04-19
duration: "50m"
tags:
  - incident
  - kafka
  - schema-registry
  - avro
  - backward-compatibility
  - payment-service
  - prod
---

## Summary

A developer registered a new Avro schema version for the `payment-events` topic that removed a required field (`currency_code`). The Schema Registry compatibility level was set to `NONE`, allowing the breaking change. Existing consumers deserialised the message and encountered a missing required field, causing NullPointerExceptions and consumer group lag to spike to 1.4 million messages over 50 minutes.

## Symptoms

- payment-service consumer logs: `NullPointerException: currency_code is null`
- Kafka consumer group `payment-processor` lag: 1,400,000 (alert threshold: 50,000)
- payment-service `/health`: returning 500 (consumer health check failing)
- payment-service events: processing halted for 50 minutes

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~2,300 payment events unprocessed (queued, not lost) |
| Services degraded | payment-service event processing |
| Revenue impact | Delayed (not lost) — payments queued in Kafka |
| Duration | 13:20 → 14:10 UTC (50 min) |
| Data loss | None — events remained in Kafka |
| SLA breach | Yes — payment processing latency SLA breached |
| Customer comms | N/A — payments delayed, not failed |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 13:15 | New schema version registered in Schema Registry |
| 13:20 | New producer starts publishing with new schema |
| 13:22 | Consumer NullPointerExceptions begin |
| 13:30 | Consumer lag alert fired |
| 13:45 | Root cause identified: schema change |
| 14:00 | Old schema re-registered; consumers resumed |
| 14:10 | Lag fully drained |

## Diagnosis

1. Checked consumer exception:
   ```bash
   kubectl logs -n payments deploy/payment-consumer | grep NullPointerException | head -5
   # NullPointerException at PaymentEvent.getCurrencyCode()
   ```
2. Inspected Schema Registry for recent changes:
   ```bash
   curl http://schema-registry:8081/subjects/payment-events-value/versions
   # [1, 2, 3, 4]  — version 4 is new
   curl http://schema-registry:8081/subjects/payment-events-value/versions/4
   # schema: { ...no currency_code field }
   ```
3. Confirmed compatibility mode:
   ```bash
   curl http://schema-registry:8081/config/payment-events-value
   # {"compatibilityLevel":"NONE"}
   ```

## Resolution

1. **Mitigate:** Reverted Schema Registry to v3 (previous compatible schema):
   ```bash
   curl -X DELETE http://schema-registry:8081/subjects/payment-events-value/versions/4
   ```
2. **Rolled back producer** to use schema v3:
   ```bash
   kubectl rollout undo deployment/payment-producer -n payments
   ```
3. **Consumers automatically recovered** once valid messages appeared
4. **Fixed:** Set compatibility level to `BACKWARD`:
   ```bash
   curl -X PUT http://schema-registry:8081/config/payment-events-value \
     -H 'Content-Type: application/json' \
     -d '{"compatibility": "BACKWARD"}'
   ```
5. **Verified consumer lag draining:**
   ```bash
   kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group payment-processor
   # LAG: 0
   ```

## Post-Incident Review

**What went well:**
- Events retained in Kafka — no data loss; processing caught up fully

**What needs improvement:**
- `NONE` compatibility level should never be used in production
- Schema changes not reviewed by consumer team before deployment

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Set all production topics to `BACKWARD` compatibility in Schema Registry | Platform | 2026-04-26 | Open |
| Add schema compatibility check to CI for any producer code change | Backend | 2026-04-26 | Open |
| Require consumer team sign-off on schema changes | Process | 2026-04-24 | Open |

## Links

- Runbooks: [[RB-014-kafka-cluster-operations]], [[RB-010-kafka-consumer-lag-remediation]]
- Related incidents: [[INC-047-kafka-producer-buffer-full]], [[INC-023-kafka-consumer-rebalance-storm]]
