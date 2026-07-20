---
id: RB-028
title: SQS Dead Letter Queue (DLQ) Recovery and Message Replay
service: "*"
related_services:
  - notification-service
  - order-service
  - payment-service
severity: SEV-2
environment: prod
category: connectivity
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - sqs
  - dlq
  - dead-letter
  - queue
  - messaging
  - prod
related_incidents:
  - "[[INC-057-sqs-dead-letter-queue-full]]"
related_runbooks:
  - "[[RB-010-kafka-consumer-lag-remediation]]"
related_guardrails: []
---

## Purpose

Diagnose why messages are landing in Dead Letter Queues and safely replay them after fixing the root cause.

**Desired outcome:** Root cause fixed, DLQ drained, all messages successfully processed.

## Success Criteria

- Root cause identified and fixed
- DLQ message count returned to 0
- Main queue processing normally (no new DLQ messages)
- All replayed messages processed successfully
- No duplicate processing side effects

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any service with SQS DLQ |
| Related services | notification-service, order-service, payment-service |
| Environments | prod, staging |
| Use when | DLQ depth growing, messages failing processing repeatedly |
| Do NOT use when | Intentional DLQ usage for async error handling |
| Risk level | Medium (replay can cause duplicate processing) |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] AWS CLI access to SQS
- [ ] Knowledge of which queue/DLQ is affected
- [ ] Access to consumer service logs
- [ ] Understanding of message idempotency guarantees

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| AWS CLI | SQS queue operations | Write access |
| `kubectl` | Consumer service logs and operations | Cluster admin |
| AWS Console | Queue metrics and monitoring | Read access |

## Trigger

- Alert: `*-DLQDepthHigh` (DLQ message count growing)
- Symptom: Expected processing not happening (notifications not sent, orders not confirmed)
- Metric: Main queue messages cycling to DLQ after max receives

## Triage

1. Check DLQ depth
   ```bash
   aws sqs get-queue-attributes --queue-url <dlq-url> \
     --attribute-names ApproximateNumberOfMessagesVisible
   ```

2. Sample a DLQ message
   ```bash
   aws sqs receive-message --queue-url <dlq-url> --max-number-of-messages 1 | jq '.Messages[0].Body'
   ```

3. Check consumer logs for error
   ```bash
   kubectl logs -l app=<consumer-service> -n <namespace> --tail=100 | grep -i "error\|exception\|failed"
   ```

## Investigation

1. **Identify failure reason from consumer logs**
   ```bash
   # Common causes: deserialization error, missing field, downstream timeout
   kubectl logs -l app=<consumer-service> -n <namespace> --tail=200 | grep -B2 -A5 "failed to process"
   ```

2. **Check if message format changed (schema evolution)**
   ```bash
   # Compare DLQ message structure with expected schema
   aws sqs receive-message --queue-url <dlq-url> --max-number-of-messages 5 | jq '.Messages[].Body | fromjson | keys'
   ```

3. **Check consumer health (is it running?)**
   ```bash
   kubectl get pods -n <namespace> -l app=<consumer-service>
   ```

4. **Decision point:**
   - IF deserialization error → fix consumer, then replay
   - IF downstream timeout → fix downstream, then replay
   - IF poison message (unfixable format) → move to permanent dead letter
   - IF consumer crashed → restart consumer, then replay

## Mitigation

### Fix root cause first, then replay:

```bash
# Fix consumer (deploy fix), then use SQS message move task:
aws sqs start-message-move-task \
  --source-arn <dlq-arn> \
  --destination-arn <main-queue-arn>
# Monitor move progress:
aws sqs list-message-move-tasks --source-arn <dlq-arn>
```

### If messages are unfixable (poison messages):

```bash
# Move to permanent archive queue for manual review:
aws sqs start-message-move-task \
  --source-arn <dlq-arn> \
  --destination-arn <archive-queue-arn>
```

**After replay:** Monitor DLQ — should remain at 0 messages.

## Verification

- [ ] DLQ message count: 0
- [ ] Main queue processing normally (no new DLQ arrivals)
- [ ] Consumer logs showing successful processing
- [ ] Expected downstream effects visible (notifications sent, orders confirmed)

```bash
aws sqs get-queue-attributes --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessagesVisible
# Expected: 0
```

## Failure Signals

- Messages keep arriving in DLQ after fix
- Replay causes duplicate processing (idempotency not working)
- Consumer crashes during replay (load-induced)

## Rollback

1. **If replay caused duplicates:** Run deduplication job specific to the service
2. **If consumer overwhelmed by replay:** Throttle replay rate by moving messages in batches

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Cannot fix root cause in 20 min | Service owner | Direct page | 15 min |
| DLQ growing rapidly (>1000/min) | Service owner + EM | #incident-response | 10 min |
| Replay caused data inconsistency | DBA + service owner | #data-eng | Immediate |

## Notes

- **Fix root cause BEFORE replaying.** Replaying into a broken consumer just refills the DLQ.
- **maxReceiveCount on the redrive policy** determines how many times a message is retried before DLQ. Default is often 3.
- **Message replay can cause duplicates** — ensure consumer logic is idempotent.
- **SQS message move task** (2023 feature) is the cleanest way to replay — no custom code needed.
- See [[INC-057-sqs-dead-letter-queue-full]] for a real-world schema incompatibility example.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Send a malformed message to staging queue, verify DLQ routing and replay procedure.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
