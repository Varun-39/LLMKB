---
id: INC-054
title: Zombie Pods After Node Network Partition — Split Brain Traffic
severity: SEV-1
service: api-gateway
environment: prod
category: outage
date: 2026-05-14
duration: "25m"
tags:
  - incident
  - kubernetes
  - network-partition
  - split-brain
  - pods
  - critical
  - prod
---

## Summary

At 08:45 UTC on 2026-05-14, a network partition isolated worker-node-03 from the control plane for 7 minutes. The node was marked `NotReady` and the pod eviction timer started (5 minutes). However, pods on the isolated node continued running and serving traffic via the external load balancer (which uses health checks, not K8s status). When the partition healed and eviction triggered, new pods were scheduled on other nodes while the old "zombie" pods continued running on node-03, causing duplicate request processing and data inconsistency.

## Symptoms

- kubelet: node-03 `NotReady` at 08:45 UTC
- Load balancer: continued routing to node-03 pods (TCP health checks passing)
- After partition healed: duplicate pods running (old on node-03 + new on other nodes)
- Payment duplicates: 47 orders processed twice
- Conflicting database writes from zombie pods

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | 47 users with duplicate order processing |
| Services degraded | api-gateway, payment-service (duplicate processing) |
| Revenue impact | $3.2K in duplicate charges (reversed) |
| Duration | 08:45 → 09:10 UTC (25 min) |
| Data loss | No loss but data duplication (47 orders) |
| SLA breach | Yes — data integrity SLA breached |
| Customer comms | 47 affected users contacted directly |

## Diagnosis

1. Confirmed node partition
   ```bash
   kubectl get nodes
   # worker-node-03: NotReady (08:45), Ready (08:52)
   ```

2. Found duplicate pods
   ```bash
   kubectl get pods -n api -l app=api-gateway -o wide
   # 6 pods running (expected 3) — 3 on node-03, 3 on other nodes
   ```

3. Load balancer routing to both sets
   ```bash
   aws elbv2 describe-target-health --target-group-arn <arn>
   # Both old and new pod IPs listed as healthy
   ```

## Resolution

1. **Mitigate:** Cordoned node-03 and deleted zombie pods
   ```bash
   kubectl cordon worker-node-03
   kubectl delete pod api-gateway-old-1 api-gateway-old-2 api-gateway-old-3 -n api --force
   ```

2. **Fix:** Reversed 47 duplicate charges via payment-service admin API

3. **Verify:** Correct pod count, no duplicate processing

## Post-Incident Review

- Load balancer health checks bypass K8s pod lifecycle (known limitation)
- Added pod disruption budgets with `pod-deletion-cost` annotation
- Configured load balancer to use K8s readiness gate (AWS ALB target group binding)
- Reduced pod eviction timeout from 5 min to 30 seconds
- Added idempotency key enforcement in payment-service

## Links

- Runbooks: [[RB-009-etcd-cluster-recovery]]
- Related incidents: [[INC-004-k8s-node-notready]], [[INC-035-mongodb-election-network-partition]]
