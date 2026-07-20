---
id: RB-010
title: Kafka Consumer Lag Remediation
service: "*"
related_services:
  - order-service
  - notification-service
  - analytics-service
severity: SEV-2
environment: prod
category: performance
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - kafka
  - consumer
  - lag
  - messaging
  - prod
related_incidents:
  - "[[INC-023-kafka-consumer-rebalance-storm]]"
  - "[[INC-047-kafka-producer-buffer-full]]"
related_runbooks:
  - "[[RB-014-kafka-cluster-operations]]"
related_guardrails: []
---

## Purpose

Diagnose and remediate Kafka consumer lag, covering slow consumers, rebalance storms, stuck offsets, and poison messages.

**Desired outcome:** Consumer lag below 1,000 messages per partition, stable consumer group with no rebalances.

## Success Criteria

- Consumer lag < 1,000 messages per partition
- Consumer group state: `Stable` (no ongoing rebalances)
- No `REBALANCE_IN_PROGRESS` errors in consumer logs
- Message processing rate >= production rate
- No messages in DLQ growing (if applicable)

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any Kafka consumer service |
| Related services | order-service, notification-service, analytics-service |
| Environments | prod, staging |
| Use when | `*-KafkaConsumerLagHigh`, `*-ConsumerGroupUnstable` alerts |
| Do NOT use when | Kafka brokers are down (check broker health first) |
| Risk level | Medium |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kafka-consumer-groups.sh` or equivalent CLI access
- [ ] Access to consumer service logs and metrics
- [ ] Knowledge of affected consumer group and topics
- [ ] Grafana access to Kafka dashboards

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kafka-consumer-groups.sh` | Consumer group diagnostics | Kafka admin |
| `kubectl` | Consumer service operations | Cluster admin |
| Grafana | Lag metrics and trends | Read access |
| Kafka UI (Kafdrop/AKHQ) | Topic inspection | Read access |

## Trigger

- Alert: `*-KafkaConsumerLagHigh` (lag >10,000 messages for >5 min)
- Alert: `*-ConsumerGroupUnstable` (repeated rebalances)
- Symptom: Messages not being processed (downstream effects visible)
- Metric: Consumer lag growing linearly on Grafana

## Triage

1. Check consumer group lag
   ```bash
   kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
     --group <consumer-group> --describe
   # What to look for: LAG column, CONSUMER-ID (empty = no active consumer)
   ```

2. Check consumer group state
   ```bash
   kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
     --group <consumer-group> --state
   # What to look for: Stable, Rebalancing, Empty, Dead
   ```

3. Wrong symptoms? Broker down? → Check `kafka-broker-api-versions.sh`

## Investigation

1. **Check if consumers are running**
   ```bash
   kubectl get pods -n <namespace> -l app=<consumer-service>
   kubectl logs -l app=<consumer-service> -n <namespace> --tail=50 | grep -i "rebalance\|error\|exception"
   ```

2. **Check for rebalance storms**
   ```bash
   kubectl logs -l app=<consumer-service> -n <namespace> --tail=200 | grep -c "Rebalance"
   # What to look for: frequent rebalance = session timeout or processing too slow
   ```

3. **Check processing time per message**
   ```bash
   kubectl logs -l app=<consumer-service> -n <namespace> --tail=50 | grep "processing.*ms"
   # What to look for: if processing > session.timeout.ms → rebalance triggered
   ```

4. **Check for poison messages (deserialization failures)**
   ```bash
   kubectl logs -l app=<consumer-service> -n <namespace> --tail=100 | grep -i "deserial\|parse\|schema"
   ```

5. **Decision point:**
   - IF no active consumers → proceed to Mitigation Option A
   - IF rebalance storm → proceed to Mitigation Option B
   - IF slow processing → proceed to Mitigation Option C
   - IF poison message blocking → proceed to Mitigation Option D
   - IF unclear → escalate (see Escalation section)

## Mitigation

### Option A: No active consumers — restart consumer service

```bash
kubectl rollout restart deployment/<consumer-service> -n <namespace>
kubectl rollout status deployment/<consumer-service> -n <namespace> --timeout=120s
```

### Option B: Rebalance storm — increase session timeout

```bash
kubectl set env deployment/<consumer-service> -n <namespace> \
  KAFKA_SESSION_TIMEOUT_MS=45000 KAFKA_MAX_POLL_INTERVAL_MS=600000
kubectl rollout restart deployment/<consumer-service> -n <namespace>
```

### Option C: Slow processing — scale consumers

```bash
kubectl scale deployment/<consumer-service> -n <namespace> \
  --replicas=<partition-count>
# Note: consumers cannot exceed partition count
```

### Option D: Poison message — skip offset

```bash
# Identify stuck offset:
kafka-consumer-groups.sh --bootstrap-server kafka:9092 --group <group> --describe
# Reset offset to skip poison message:
kafka-consumer-groups.sh --bootstrap-server kafka:9092 --group <group> \
  --topic <topic>:<partition> --reset-offsets --shift-by 1 --execute
```

**After mitigation:** Monitor for 10 minutes — lag decreasing, no rebalances, processing rate stable.

## Verification

- [ ] Consumer lag decreasing (trend going down)
- [ ] Consumer group state: `Stable`
- [ ] No rebalance events in logs for 10 minutes
- [ ] Processing rate >= production rate on Grafana

```bash
kafka-consumer-groups.sh --bootstrap-server kafka:9092 --group <group> --describe
# Expected: LAG decreasing, all partitions assigned
```

## Failure Signals

- Lag continues growing despite scaled consumers
- Rebalances continue after timeout increase
- Consumer pods crashing (different root cause)
- DLQ growing (messages failing processing)

**If any failure signal is present:** Do NOT repeat. Proceed to Escalation.

## Rollback

1. **Undo scale-out:** `kubectl scale deployment/<consumer> -n <namespace> --replicas=<original>`
2. **Undo timeout change:** Remove env vars, restart
3. **Undo offset reset:** Cannot undo — message was skipped. Check DLQ for recovery.

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Lag still growing after 20 min | Service owner | Direct page | 10 min |
| Rebalance won't stabilize | Kafka platform team | #platform-support | 15 min |
| Broker-level issue suspected | Kafka admin | #data-eng | 10 min |
| Data loss risk (skipped messages) | Service owner + EM | #incident-response | 5 min |

## Notes

- **Consumers cannot exceed partition count.** If you have 6 partitions, max 6 consumers will be active.
- **Session timeout too low** is the #1 cause of rebalance storms. Default 10s is too aggressive for services doing DB writes per message.
- **max.poll.interval.ms** is the time between polls. If processing takes longer than this, consumer is kicked from group.
- **Poison messages** block the partition. Either skip or implement dead letter queue pattern.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Produce test messages to staging topic, pause consumer, verify lag detection and remediation steps.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
