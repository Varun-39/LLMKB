---
id: RB-014
title: Kafka Cluster Operations and Broker Recovery
service: kafka
related_services:
  - order-service
  - notification-service
  - analytics-service
severity: SEV-1
environment: prod
category: connectivity
risk_level: high
estimated_duration: "30m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - kafka
  - broker
  - cluster
  - messaging
  - prod
related_incidents:
  - "[[INC-023-kafka-consumer-rebalance-storm]]"
  - "[[INC-047-kafka-producer-buffer-full]]"
related_runbooks:
  - "[[RB-010-kafka-consumer-lag-remediation]]"
related_guardrails: []
---

## Purpose

Diagnose and recover from Kafka broker failures, under-replicated partitions, and cluster instability.

**Desired outcome:** All brokers online, ISR (in-sync replicas) at full count, no under-replicated partitions, producer/consumer traffic flowing normally.

## Success Criteria

- All Kafka brokers reporting in ZooKeeper/KRaft controller
- Under-replicated partitions: 0
- Producer error rate: 0%
- Consumer lag not growing
- ISR count = replication factor for all partitions

## Scope

| Attribute | Value |
|-----------|-------|
| Service | kafka |
| Related services | order-service, notification-service, analytics-service |
| Environments | prod |
| Use when | `*-KafkaBrokerDown`, `*-UnderReplicatedPartitions`, producer errors |
| Do NOT use when | Issue is consumer-side only (use [[RB-010-kafka-consumer-lag-remediation]]) |
| Risk level | High (broker operations can cause data loss if mishandled) |
| Estimated duration | 25–30 minutes |
| Approval required | No (but data team notified for partition reassignment) |

## Prerequisites

- [ ] Kafka admin CLI tools (`kafka-topics.sh`, `kafka-reassign-partitions.sh`)
- [ ] Access to Kafka broker nodes/pods
- [ ] ZooKeeper/KRaft access for cluster state
- [ ] Knowledge of cluster topology (broker IDs, rack awareness)

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| Kafka admin scripts | Cluster diagnostics | Kafka admin |
| `kubectl` | Broker pod operations | Cluster admin |
| ZooKeeper CLI (`zookeeper-shell.sh`) | Cluster metadata | Admin |
| Grafana | Kafka cluster dashboards | Read access |

## Trigger

- Alert: `*-KafkaBrokerDown`
- Alert: `*-UnderReplicatedPartitions` (>0 for >5 min)
- Symptom: Producers receiving `NotLeaderForPartitionException`
- Symptom: Consumer groups in `PreparingRebalance` state

## Triage

1. Check broker status
   ```bash
   kafka-broker-api-versions.sh --bootstrap-server kafka:9092
   # What to look for: which brokers respond
   ```

2. Check under-replicated partitions
   ```bash
   kafka-topics.sh --bootstrap-server kafka:9092 --describe --under-replicated-partitions
   # What to look for: partition count, affected topics
   ```

3. Check controller status
   ```bash
   kafka-metadata.sh --snapshot /var/kafka-logs/__cluster_metadata-0/00000000000000000000.log --cluster-id <id>
   # Or ZK: zookeeper-shell.sh zk:2181 get /controller
   ```

## Investigation

1. **Check failed broker logs**
   ```bash
   kubectl logs kafka-<broker-id> -n kafka --tail=200
   # What to look for: OOM, disk full, network errors
   ```

2. **Check disk space on broker**
   ```bash
   kubectl exec kafka-<broker-id> -n kafka -- df -h /var/kafka-logs
   ```

3. **Check ISR shrink events**
   ```bash
   kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic <topic> | grep -v "Isr: [0-9]*,[0-9]*,[0-9]*"
   # Partitions with ISR < replication factor
   ```

4. **Decision point:**
   - IF broker disk full → proceed to Mitigation Option A
   - IF broker OOM → proceed to Mitigation Option B
   - IF broker won't start → proceed to Mitigation Option C
   - IF partition leader election needed → proceed to Mitigation Option D

## Mitigation

### Option A: Broker disk full

```bash
# Delete old log segments (retention-based):
kafka-delete-records.sh --bootstrap-server kafka:9092 --offset-json-file offsets.json
# Or expand volume (see [[RB-003-disk-space-full]])
```

### Option B: Broker OOM

```bash
kubectl set resources statefulset/kafka -n kafka --limits=memory=8Gi
kubectl delete pod kafka-<broker-id> -n kafka
```

### Option C: Broker won't start — rejoin cluster

```bash
# Clear corrupted log segment (if identified):
kubectl exec kafka-<broker-id> -n kafka -- rm /var/kafka-logs/<topic>-<partition>/00000000000000000000.log.corrupted
kubectl delete pod kafka-<broker-id> -n kafka
```

### Option D: Preferred leader election

```bash
kafka-leader-election.sh --bootstrap-server kafka:9092 \
  --election-type preferred --all-topic-partitions
```

**After mitigation:** Monitor for 15 minutes — all brokers online, ISR full, no under-replicated partitions.

## Verification

- [ ] All brokers responding
- [ ] Under-replicated partitions: 0
- [ ] Producer error rate: 0%
- [ ] Consumer lag not growing
- [ ] ISR = replication factor

```bash
kafka-topics.sh --bootstrap-server kafka:9092 --describe --under-replicated-partitions
# Expected: no output (0 under-replicated)
```

## Failure Signals

- Broker crashes again after restart
- Under-replicated partitions growing
- Producer timeout errors continuing
- ZooKeeper session expired errors

**If any failure signal is present:** Escalate immediately.

## Rollback

1. **If partition reassignment broke things:** Cancel reassignment
2. **If broker data corrupted:** Restore from replica (let it catch up via replication)

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Multiple brokers down (quorum risk) | Data platform team + EM | PagerDuty P1 | Immediate |
| Data loss suspected | Data platform + service owners | #incident-response | Immediate |
| Cannot restart broker after 3 attempts | Kafka admin | #data-eng | 10 min |
| Full cluster outage | EM + CTO | PagerDuty P1 | Immediate |

## Notes

- **Never delete Kafka data directories** unless you're sure the data is replicated elsewhere.
- **min.insync.replicas** determines how many replicas must acknowledge writes. If ISR drops below this, producers get errors.
- **Broker restart can trigger consumer rebalance.** Warn consumer teams before planned restarts.
- **Preferred leader election** should be run after a broker recovers to rebalance partition leadership.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Kill a broker in staging, verify partition failover and recovery.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Data Platform Team | Initial publication |
