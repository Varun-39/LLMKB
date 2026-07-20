---
id: RB-039
title: Kafka Schema Registry Compatibility Failure Recovery
service: payment-service
related_services:
  - reporting-service
  - auth-service
severity: SEV-2
environment: prod
category: connectivity
risk_level: high
estimated_duration: "30m"
approval_required: yes
approver_role: Backend Lead
tags:
  - runbook
  - kafka
  - schema-registry
  - avro
  - compatibility
  - consumer-lag
  - prod
---

## Purpose

Recover from a Kafka Schema Registry breaking change that causes consumer deserialization failures and consumer group lag to accumulate.

**Desired outcome:** Consumers deserialising messages successfully, consumer lag draining, no deserialization errors in logs.

## Success Criteria

- Consumer group lag < 1,000 messages and trending to 0
- No deserialization errors in consumer logs for 5 consecutive minutes
- Schema Registry compatibility level set to `BACKWARD` or stricter
- Producer and consumer using compatible schema versions

## Scope

| Attribute | Value |
|-----------|-------|
| Service | payment-service, any service consuming Kafka with Avro/JSON Schema |
| Environments | prod |
| Use when | Consumer lag spiking, deserialization errors in consumer logs, schema mismatch |
| Do NOT use when | Consumer lag due to throughput (not deserialization errors) — use RB-010 instead |
| Risk level | High — schema rollback may require producer rollback |
| Estimated duration | 25–30 minutes |
| Approval required | Yes — Backend Lead |

## Prerequisites

- [ ] Access to Schema Registry admin API
- [ ] `kafka-consumer-groups.sh` access to Kafka cluster
- [ ] Know the last known-good schema version number
- [ ] `kubectl` access to producer and consumer deployments

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| Schema Registry API (curl) | Inspect, revert, set compatibility | Admin |
| `kafka-consumer-groups.sh` | Monitor consumer lag | Read access |
| `kubectl` | Roll back producer | Namespace admin |

## Trigger

- Alert: `kafka_consumer_lag > 50000` on any group
- Log pattern: `NullPointerException`, `SchemaParseException`, `Unknown magic byte` in consumer logs
- Symptom: Consumer group lag accumulating while producers are active

## Triage

1. Confirm deserialization errors (not throughput lag):
   ```bash
   kubectl logs -n <namespace> deploy/<consumer> | grep -E "SchemaException|NullPointerException|deseri" | tail -10
   # If no deserialization errors → different issue, try RB-010
   ```
2. Check recent schema versions:
   ```bash
   curl http://schema-registry:8081/subjects/<topic>-value/versions
   # Compare latest version timestamp to when lag started
   ```
3. If timestamps align → schema change is the cause.

## Investigation

1. **Inspect the breaking schema change**
   ```bash
   curl http://schema-registry:8081/subjects/<topic>-value/versions/latest
   # Compare to previous version — look for removed/renamed required fields
   ```
2. **Check current compatibility level**
   ```bash
   curl http://schema-registry:8081/config/<topic>-value
   # Expected: BACKWARD — if NONE, that's why the breaking change was allowed
   ```
3. **Identify the first failing offset** to understand lag scope
   ```bash
   kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
     --describe --group <consumer-group>
   # LAG column per partition
   ```
4. **Decision point:**
   - IF bad schema version was just registered and no consumers have it yet → Option A (delete version)
   - IF producer is actively publishing with bad schema → Option A + Option B (rollback producer)
   - IF messages are already in topic with bad schema → Option C (skip + replay)

## Mitigation

### Option A: Delete the bad schema version

```bash
# ⚠️ Requires approval — this is irreversible
curl -X DELETE http://schema-registry:8081/subjects/<topic>-value/versions/<bad-version>
# Verify rollback:
curl http://schema-registry:8081/subjects/<topic>-value/versions/latest
```

### Option B: Roll back the producer deployment

```bash
kubectl rollout undo deployment/<producer> -n <namespace>
kubectl rollout status deployment/<producer> -n <namespace>
# Confirm producer is back to previous schema version
```

### Option C: Reset consumer offset past bad messages (last resort)

```bash
# ⚠️ Data loss risk — skip unprocessable messages
kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --group <consumer-group> \
  --topic <topic> \
  --reset-offsets --to-latest --execute
```

**After mitigation:** Set compatibility level to prevent recurrence:
```bash
curl -X PUT http://schema-registry:8081/config/<topic>-value \
  -H 'Content-Type: application/json' \
  -d '{"compatibility": "BACKWARD"}'
```

## Verification

- [ ] Consumer lag trending to 0
- [ ] No deserialization errors in consumer logs for 5 minutes
- [ ] Schema Registry `compatibilityLevel` = `BACKWARD`

```bash
kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --describe --group <consumer-group> | grep -v "^$"
# Expected: LAG = 0 across all partitions
```

## Failure Signals

- Consumer lag not decreasing after schema rollback (bad messages already in topic)
- Producer continues publishing with bad schema (rollback didn't take)
- Schema delete blocked (hard-delete requires Schema Registry in non-readonly mode)

## Rollback

- Schema deletion is irreversible — ensure backup of schema definition before deleting:
  ```bash
  curl http://schema-registry:8081/subjects/<topic>-value/versions/<bad-version> > schema-backup.json
  ```
- If offset reset (Option C) was applied, the skipped messages are not recoverable from Kafka (unless archived in S3/object store).

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Data already produced with bad schema + no archive | Backend Lead + Data Eng | #data-eng | Immediate |
| Schema Registry inaccessible | Platform team | #platform-support | 10 min |
| Lag > 1M and growing | Backend Lead + SRE | #incident-response | 5 min |

## Notes

- **`NONE` compatibility should never be used in production.** Always `BACKWARD` minimum.
- Consumer auto-recovery after schema rollback is immediate once producers emit valid messages.
- See [[INC-089-kafka-schema-registry-backward-incompatible-change]] for the incident that motivated this runbook.

## Maintenance

- **Last tested:** 2026-05-19
- **Review cycle:** Quarterly
- **Next review:** 2026-08-19
- **Test method:** Register a breaking schema in staging, trigger consumer failure, execute runbook.

## last Updated

| Date | Author | Change |
|------|--------|--------|
| 2026-05-19 | Backend Team | Initial publication |
