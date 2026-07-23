---
id: INC-057
title: SQS Dead Letter Queue Filling — Poison Messages Blocking Processing
severity: SEV-2
service: notification-service
environment: prod
category: degradation
date: 2026-05-20
duration: "55m"
tags:
  - incident
  - sqs
  - queue
  - dead-letter
  - poison-message
  - high
  - prod
error_family: unknown
resolution_runbook: RB-014
resolution_outcome: resolved
---

## Summary

At 09:00 UTC on 2026-05-20, a schema change in the order-service event payload broke deserialization in notification-service. Every message failed processing 3 times and landed in the dead letter queue. The DLQ reached 45,000 messages before the issue was identified. No notifications (email, SMS, push) were sent for 55 minutes affecting 12,000 orders.

## Symptoms

- CloudWatch: `ApproximateNumberOfMessagesVisible` on DLQ climbing at 800/min
- notification-service logs: `com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException: Unrecognized field "shipping_method"`
- Main queue: messages cycling through receive → fail → receive (3x) → DLQ
- Email/SMS delivery rate: dropped to 0

## Diagnosis

1. Confirmed DLQ growth
   ```bash
   aws sqs get-queue-attributes --queue-url <dlq-url> \
     --attribute-names ApproximateNumberOfMessagesVisible
   # 45,000
   ```

2. Sampled a DLQ message
   ```bash
   aws sqs receive-message --queue-url <dlq-url> --max-number-of-messages 1
   # Body contains new field "shipping_method" not in notification-service schema
   ```

3. order-service v5.2.0 deployed 30 minutes prior, added `shipping_method` to event

## Resolution

1. **Mitigate:** Deployed notification-service with `@JsonIgnoreProperties(ignoreUnknown = true)` to accept unknown fields
   ```bash
   kubectl set image deployment/notification-service -n notifications \
     notification-service=registry.internal/notification-service:v3.4.1-hotfix
   ```

2. **Fix:** Replayed DLQ messages back to main queue
   ```bash
   aws sqs start-message-move-task --source-arn <dlq-arn> --destination-arn <main-queue-arn>
   ```

3. **Verify:** All 45,000 messages processed, notifications sent

## Post-Incident Review

- Strict deserialization rejected messages with unknown fields
- All consumers now use `ignoreUnknown=true` by default
- Added schema compatibility check to CI: new event fields must be backward-compatible
- Added DLQ depth alert: >100 messages in 5 minutes, page immediately

## Links

- Runbooks: [[RB-014-kafka-cluster-operations]]
- Related incidents: [[INC-047-kafka-producer-buffer-full]]
