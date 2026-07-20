---
id: RB-008
title: Network Saturation / NIC Throughput Limit
service: "*"
related_services:
  - api-gateway
  - reporting-service
severity: SEV-2
environment: prod
category: performance
risk_level: medium
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - network
  - nic
  - throughput
  - infra
  - kubernetes
  - prod
related_incidents:
  - "[[INC-021-nic-saturation-api-node]]"
related_runbooks:
  - "[[RB-004-high-cpu-usage]]"
  - "[[RB-007-pod-crash-investigation]]"
related_guardrails: []
---

## Purpose

Diagnose and resolve network throughput saturation on Kubernetes nodes, covering identification of bandwidth-consuming workloads, workload isolation, and traffic management.

**Desired outcome:** Node network throughput below 70% of instance limit, API latency at pre-incident baseline, no TCP retransmits above normal rate.

## Success Criteria

Before closing the incident or declaring the runbook complete, ALL of the following must be true:

- Node network throughput below 70% of instance NIC limit
- API latency returned to baseline (P95 < 300ms)
- TCP retransmit rate < 0.5%
- No active latency or timeout alerts for 15 minutes
- Offending workload isolated or removed from affected node

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any service on a network-saturated node |
| Related services | api-gateway, reporting-service |
| Environments | prod, staging |
| Use when | `*-NetworkSaturation`, `*-HighLatency` with NIC metrics at ceiling, or elevated TCP retransmits |
| Do NOT use when | Latency is caused by CPU/memory pressure (check those metrics first) |
| Risk level | Medium |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] SSH access to affected node
- [ ] `kubectl` access to affected cluster
- [ ] Grafana/CloudWatch access to network metrics
- [ ] Knowledge of instance type NIC limits (e.g., `c5.2xlarge` = 10 Gbps)

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| SSH + `sar`, `iftop`, `netstat` | Network diagnostics on node | sudo access |
| `kubectl` | Pod placement and operations | Cluster admin |
| Grafana / CloudWatch | Network throughput metrics | Read access |
| AWS Console | Instance type verification | Read access |

## Trigger

- Alert: `*-NetworkSaturation` or `*-NICThroughputHigh`
- Metric: Node network out/in at >85% of instance NIC baseline for >3 min
- Symptom: Elevated TCP retransmit rate (>2%) on specific node
- Symptom: API latency increase isolated to pods on a specific node (other nodes unaffected)
- Symptom: `ConnectionTimeoutException` spike from services on one node

## Triage

1. Confirm network saturation on the affected node
   ```bash
   # On node:
   sar -n DEV 1 5
   # What to look for: txkB/s or rxkB/s near instance limit
   # e.g., c5.2xlarge limit = 10 Gbps ≈ 1,250,000 kB/s
   ```

2. Assess blast radius — single node or cluster-wide
   ```bash
   # Check CloudWatch NetworkOut for all nodes
   # OR: kubectl top nodes (won't show network, but shows which nodes are under load)
   kubectl get pods -o wide | grep <node-name>
   # What to look for: which services are affected on this node
   ```

3. Wrong symptoms? CPU/memory also saturated? → Try [[RB-004-high-cpu-usage]] or [[RB-002-kubernetes-oom-remediation]]

## Investigation

1. **Identify top network consumers on the node**
   ```bash
   ssh ec2-user@<node-ip>
   iftop -n -i eth0 -t -s 10
   # What to look for: which pod/IP is consuming the most bandwidth
   # Large outbound transfer to S3/external = bulk export job
   ```

2. **Check TCP retransmit rate** (confirms congestion)
   ```bash
   netstat -s | grep retransmitted
   # What to look for: high retransmit count = NIC congestion causing packet loss
   ```

3. **Identify the pod causing the saturation**
   ```bash
   kubectl get pods --all-namespaces -o wide | grep <node-name>
   # Cross-reference with the IP identified by iftop
   kubectl get pod <pod-name> -n <namespace> -o wide
   ```

4. **Confirm API latency is isolated to this node**
   ```bash
   # Check if API pods on OTHER nodes have normal latency
   kubectl top pods -n <namespace> -l app=<service> -o wide
   # If only pods on the saturated node are slow → confirmed NIC issue
   ```

5. **Check for bulk data transfer jobs**
   ```bash
   kubectl get jobs --all-namespaces | grep -i "export\|batch\|backup\|transfer"
   kubectl get pods --all-namespaces -o wide | grep <node-name> | grep -i "export\|batch"
   ```

6. **Decision point:**
   - IF bulk export/transfer job identified → proceed to Mitigation Option A
   - IF sustained high traffic on API pods (legitimate load) → proceed to Mitigation Option B
   - IF no clear culprit but NIC saturated → proceed to Mitigation Option C
   - IF unclear → escalate (see Escalation section)

## Mitigation

### Option A: Kill or reschedule the bandwidth-consuming workload

```bash
# Delete the export/batch pod:
kubectl delete pod <export-pod-name> -n <namespace>
# Or delete the job entirely:
kubectl delete job <job-name> -n <namespace>
# Network saturation should resolve within 30 seconds
```

### Option B: Drain latency-sensitive pods off the saturated node

```bash
# Cordon the node to prevent new scheduling:
kubectl cordon <node-name>
# Delete API pods to force reschedule to other nodes:
kubectl delete pod <api-pod-1> <api-pod-2> -n <namespace>
# Pods will reschedule to non-saturated nodes
```

### Option C: Drain the entire node for maintenance

```bash
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
# All pods will be rescheduled to other nodes
# Node can then be investigated or replaced
```

**After mitigation:** Monitor for 5–10 minutes — network throughput back to baseline, API latency normalized, TCP retransmits < 0.5%.

## Verification

- [ ] Node network throughput below 70% of instance limit
- [ ] API P95 latency at baseline (< 300ms)
- [ ] TCP retransmit rate < 0.5%
- [ ] No active latency or timeout alerts for 15 minutes
- [ ] Offending workload removed from the node

```bash
# On node:
sar -n DEV 1 5
# Expected: txkB/s well below NIC limit

# On cluster:
kubectl get pods -n <namespace> -l app=<service>
# Expected: all pods Running on healthy nodes
curl -s -o /dev/null -w "%{http_code}" https://<service-endpoint>/health
# Expected: 200
```

## Failure Signals

If the mitigation did NOT work, you will observe one or more of the following:

- Network throughput remains at ceiling after removing the identified workload
- API latency does not improve despite pod rescheduling
- TCP retransmits continue at high rate
- New pods on other nodes also experiencing latency (not a single-node issue)
- The bandwidth consumer respawns immediately (CronJob or controller)

**If any failure signal is present after mitigation:** Do NOT repeat the same step. Proceed to Rollback or Escalation immediately.

## Rollback

1. **If you cordoned a node unnecessarily:**
   ```bash
   kubectl uncordon <node-name>
   ```

2. **If you killed a batch job that was critical:**
   ```bash
   # Reschedule to a dedicated export node:
   kubectl apply -f <job-manifest-with-node-affinity>
   ```

3. **If draining the node caused capacity issues:**
   ```bash
   kubectl uncordon <node-name>
   ```

4. Notify #incident-response: "Rollback executed — escalating."

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| NIC saturation on multiple nodes simultaneously | Platform/SRE team | #platform-support | 10 min response |
| Cannot identify bandwidth consumer | Network/infra team | #platform-support | 10 min response |
| Latency not resolving after workload isolation | Senior on-call + EM | PagerDuty | 5 min response |
| Need larger instance type or dedicated node pool | Platform team (capacity) | #platform-support | 30 min response |

## Notes

- **Instance NIC limits are often overlooked.** Common limits: `c5.large` = 10 Gbps, `c5.xlarge` = 10 Gbps, `c5.2xlarge` = 10 Gbps, `c5.4xlarge` = 10 Gbps (up to). Check AWS docs for exact baseline vs. burst limits.
- **NIC saturation looks like CPU saturation** to application metrics (high latency, timeouts). The differentiator: CPU usage is normal but latency is elevated → check network first.
- **Bulk data transfers should never co-locate with latency-sensitive services.** Use `podAntiAffinity` rules or dedicated node pools for export/batch workloads.
- **TCP retransmit rate >2%** is a strong indicator of network congestion. Normal rate is <0.1%.
- **This issue frequently recurs** when batch jobs are rescheduled without node affinity rules. Ensure anti-affinity is applied permanently, not just as incident mitigation.
- See also: [[INC-021-nic-saturation-api-node]]

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Schedule a large S3 transfer on a staging node running API pods, verify latency degradation, then execute runbook isolation steps.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
