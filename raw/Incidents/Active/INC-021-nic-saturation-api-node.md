---
id: INC-021
title: NIC Saturation on API Node — Network Throughput Limit Hit
severity: SEV-2
service: api-gateway
environment: prod
category: degradation
status: resolved
owner: Marcus Webb
assigned-to: Marcus Webb
date: 2026-02-13
duration: 33 minutes
created: 2026-02-13
updated: 2026-02-13
tags:
  - incident
  - infra
  - network
  - nic
  - throughput
  - high
  - prod
  - api
related_runbooks:
  - "[[RB-003-high-cpu]]"
related_incidents:
  - "[[INC-004-k8s-node-notready]]"
  - "[[INC-007-high-cpu-payment-service]]"
---

# INC-021 — NIC Saturation on API Node: Network Throughput Limit Hit

## Summary

At 13:45 UTC on 2026-02-13, node `ip-10-0-1-82` running api-gateway pods hit the 10 Gbps NIC throughput ceiling due to a reporting-service bulk export job transferring a 40 GB report via the same node. API response time degraded as network I/O queued behind the export. Latency on `/api/` endpoints served from this node doubled for 33 minutes until the bulk export completed and node was drained for maintenance.

## Symptoms

- Grafana: `ip-10-0-1-82` network out at 9.8 Gbps (limit: 10 Gbps) from 13:45 UTC
- P95 latency on api-gateway endpoints: 195 ms → 890 ms
- CloudWatch: `NetworkOut` metric for instance at 99% of baseline limit
- TCP retransmit rate on node: 8.4% (normal: <0.2%)
- Sentry: `ConnectionTimeoutException` increase from api-gateway
- No pod restarts or CPU/memory pressure

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~3,400 users hitting api-gateway pods on affected node |
| Services degraded | api-gateway (latency degradation only — 2/6 pods affected) |
| Revenue impact | ~$4K in degraded checkout completion rates |
| Duration | 13:45 → 14:18 UTC (33 min) |
| Data loss | None |

## Possible Causes

1. **Bulk export co-located with API pods** — reporting-service export job scheduled on the same node as api-gateway pods, monopolizing NIC
2. **No network I/O limit on reporting pods** — reporting bulk transfers not isolated to dedicated export nodes
3. **Instance type undersized for mixed workloads** — `c5.2xlarge` has 10 Gbps baseline; insufficient for API + bulk export concurrently
4. **No pod affinity/anti-affinity rules** — bulk export workloads not isolated from latency-sensitive API workloads

## Troubleshooting Steps

1. Identified network saturation
   ```bash
   # On node ip-10-0-1-82:
   sar -n DEV 1 5
   # eth0: rxkB/s 1,124,381  txkB/s 1,198,452 — ~9.8 Gbps out
   ```

2. Identified top network consumers
   ```bash
   iftop -n -i eth0 -t -s 10
   # Top source: 10.0.4.12 (reporting-svc-export-xxx) → 10.0.9.55 (S3)
   # Transfer: 8.9 Gbps
   ```

3. Confirmed network pressure correlated with TCP retransmits
   ```bash
   netstat -s | grep retransmitted
   # 84,231 segments retransmitted (measured over 5 min window)
   ```

4. Checked pod placement for reporting export
   ```bash
   kubectl get pod reporting-svc-export-batch -n reporting -o wide
   # Node: ip-10-0-1-82  ← co-located with api-gateway pods
   ```

5. Confirmed api-gateway latency was isolated to pods on this node (other nodes unaffected)

## Resolution

1. Deleted the export job pod (bulk export rescheduled to off-hours)
   ```bash
   kubectl delete pod reporting-svc-export-batch -n reporting
   ```

2. Network saturation resolved within 30 seconds; latency returned to baseline

3. Drained the node for maintenance window to add anti-affinity rules
   ```bash
   kubectl drain ip-10-0-1-82 --ignore-daemonsets --delete-emptydir-data
   ```

4. Applied `podAntiAffinity` rule to reporting export jobs — must not schedule on nodes with `app=api-gateway`

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| API latency >2× baseline on multiple nodes | Escalate to platform team | #platform-support |
| NIC at 100% with no obvious culprit | Engage network/infra team | #platform-support |
| Cannot isolate workload within 10 min | Drain affected node | #incident-response |

## Post-Incident Notes

**Went well:**
- Network saturation identified quickly via `sar` and `iftop`
- Killing the export pod immediately resolved latency without any service disruption

**Improve:**
- No workload isolation policy — bulk transfers and API pods could co-locate
- No NIC utilization alert

**Action items:**
- [x] Deleted export job, drained node
- [x] Applied pod anti-affinity: reporting exports cannot land on API nodes
- [ ] Add Grafana alert: node network throughput >70% of instance limit
- [ ] Move bulk data transfers to dedicated export node pool with high-network instance types

## Related Runbooks

- [[RB-003-high-cpu]]
