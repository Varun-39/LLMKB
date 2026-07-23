---
id: INC-021
title: NIC Saturation on API Node — Network Throughput Limit Hit
severity: SEV-2
service: api-gateway
environment: prod
category: degradation
date: 2026-02-13
duration: "33m"
detection_gap: "2m"
tags:
  - incident
  - infra
  - network
  - nic
  - throughput
  - high
  - prod
  - api
error_family: memory-pressure
resolution_runbook: RB-008
resolution_outcome: resolved
---

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
| SLA breach | No — partial degradation stayed within SLA threshold |
| Customer comms | N/A — partial latency increase, no status page update |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 13:45 | NIC throughput hit ceiling on ip-10-0-1-82 |
| 13:47 | P95 latency doubled on affected api-gateway pods |
| 13:49 | On-call acknowledged (Marcus Webb) |
| 13:52 | Network saturation identified via `sar` |
| 13:55 | Reporting bulk export pod identified as NIC consumer |
| 13:58 | Export pod deleted to free NIC bandwidth |
| 14:00 | Latency returned to baseline |
| 14:10 | Node drained for maintenance |
| 14:18 | Anti-affinity rules applied, incident closed |

## Diagnosis

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

1. **Mitigate:** Deleted the export job pod to immediately free NIC bandwidth
   ```bash
   kubectl delete pod reporting-svc-export-batch -n reporting
   ```

2. **Fix:** Drained the node and applied `podAntiAffinity` rule to reporting export jobs
   ```bash
   kubectl drain ip-10-0-1-82 --ignore-daemonsets --delete-emptydir-data
   # Applied podAntiAffinity: reporting exports cannot land on nodes with app=api-gateway
   ```

3. **Verify:** Network saturation resolved within 30 seconds; latency returned to baseline
   ```bash
   sar -n DEV 1 5
   # eth0: txkB/s ~120,000 — normal baseline
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| API latency >2× baseline on multiple nodes | Escalate to platform team | #platform-support |
| NIC at 100% with no obvious culprit | Engage network/infra team | #platform-support |
| Cannot isolate workload within 10 min | Drain affected node | #incident-response |

## Post-Incident Review

**What went well:**
- Network saturation identified quickly via `sar` and `iftop`
- Killing the export pod immediately resolved latency without any service disruption

**What needs improvement:**
- No workload isolation policy — bulk transfers and API pods could co-locate
- No NIC utilization alert existed

**Contributing factors (beyond root cause):**
- Reporting bulk export job scheduled on same node as latency-sensitive API pods
- No network I/O limits or pod anti-affinity rules for bulk transfer workloads
- Instance type (`c5.2xlarge`, 10 Gbps) undersized for mixed API + bulk export workloads

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Delete export job, drain node | Marcus Webb | 2026-02-13 | Done |
| Apply pod anti-affinity: reporting exports cannot land on API nodes | Marcus Webb | 2026-02-13 | Done |
| Add Grafana alert: node network throughput >70% of instance limit | SRE team | 2026-02-27 | Open |
| Move bulk data transfers to dedicated export node pool with high-network instance types | Platform team | 2026-03-06 | Open |

## Links

- Runbooks: [[RB-008-network-saturation-throughput]]
- Related incidents: [[INC-004-k8s-node-notready]], [[INC-007-high-cpu-payment-service]]
- PR/commit: N/A
- Post-mortem doc: N/A
