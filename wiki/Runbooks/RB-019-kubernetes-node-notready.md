---
id: RB-019
title: Kubernetes Node NotReady Recovery
service: kubernetes-nodes
related_services:
  - kubelet
  - kube-proxy
  - all-services
severity: SEV-2
environment: prod
category: resource-exhaustion
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - kubernetes
  - node
  - notready
  - kubelet
  - prod
related_incidents:
  - "[[INC-004-k8s-node-notready]]"
  - "[[INC-054-zombie-pods-node-network-partition]]"
  - "[[INC-063-node-clock-skew-tls-failures]]"
related_runbooks:
  - "[[RB-003-disk-space-full]]"
  - "[[RB-002-kubernetes-oom-remediation]]"
related_guardrails: []
---

## Purpose

Diagnose and recover from Kubernetes nodes entering NotReady state, covering kubelet failures, network partitions, disk pressure, and resource exhaustion.

**Desired outcome:** All nodes in Ready state, pods rescheduled and running, no workload interruption.

## Success Criteria

- All nodes showing `Ready` condition
- Pods previously on NotReady node rescheduled and running
- kubelet reporting healthy on affected node
- No remaining DiskPressure, MemoryPressure, or PIDPressure conditions
- Node allocatable resources confirmed sufficient

## Scope

| Attribute | Value |
|-----------|-------|
| Service | kubernetes-nodes |
| Related services | kubelet, kube-proxy, all services with pods on affected node |
| Environments | prod, staging |
| Use when | `*-NodeNotReady` alert, node showing NotReady in `kubectl get nodes` |
| Do NOT use when | Planned node maintenance (cordon/drain workflow instead) |
| Risk level | Medium |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to cluster
- [ ] SSH access to affected node (if reachable)
- [ ] AWS Console access (for instance health)
- [ ] Knowledge of which node is affected

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Node and pod operations | Cluster admin |
| SSH | Node-level diagnostics | sudo |
| AWS Console/CLI | Instance health checks | Read access |
| `systemctl` | kubelet service management | sudo |

## Trigger

- Alert: `*-NodeNotReady`
- `kubectl get nodes` showing `NotReady` status
- Pods on node entering `Terminating` or `Unknown` state
- kubelet heartbeat missing from API server

## Triage

1. Confirm node status
   ```bash
   kubectl get nodes -o wide
   kubectl describe node <node-name> | grep -A10 "Conditions"
   # What to look for: Ready=False or Ready=Unknown, other pressure conditions
   ```

2. Check if node is reachable
   ```bash
   ssh ec2-user@<node-ip> "echo reachable"
   # If unreachable → network partition or instance down
   ```

3. Check AWS instance status
   ```bash
   aws ec2 describe-instance-status --instance-ids <instance-id>
   # What to look for: impaired, insufficient-data
   ```

## Investigation

1. **If node is reachable — check kubelet**
   ```bash
   ssh ec2-user@<node-ip>
   systemctl status kubelet
   journalctl -u kubelet --since "10 min ago" | tail -50
   # What to look for: restart loops, certificate errors, OOM
   ```

2. **Check for resource pressure**
   ```bash
   df -h /var/lib/kubelet
   free -h
   # What to look for: disk full, memory exhausted
   ```

3. **Check container runtime**
   ```bash
   systemctl status containerd
   crictl ps | wc -l
   ```

4. **Decision point:**
   - IF kubelet crashed → proceed to Mitigation Option A
   - IF disk pressure → proceed to Mitigation Option B
   - IF node unreachable → proceed to Mitigation Option C
   - IF instance impaired → proceed to Mitigation Option D

## Mitigation

### Option A: Restart kubelet

```bash
ssh ec2-user@<node-ip>
sudo systemctl restart kubelet
# Wait 30s for node to re-register
```

### Option B: Clear disk pressure

```bash
ssh ec2-user@<node-ip>
sudo docker system prune -af
sudo journalctl --vacuum-time=1h
# See [[RB-003-disk-space-full]] for detailed steps
```

### Option C: Node unreachable — drain and replace

```bash
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force --timeout=60s
# If instance is truly dead, terminate and let ASG replace:
aws ec2 terminate-instances --instance-ids <instance-id>
```

### Option D: Instance impaired — replace

```bash
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force
aws ec2 terminate-instances --instance-ids <instance-id>
# ASG will launch replacement
```

**After mitigation:** Verify node Ready, pods rescheduled.

## Verification

- [ ] Node showing `Ready`
- [ ] No pressure conditions (Disk, Memory, PID)
- [ ] Pods rescheduled and Running
- [ ] kubelet healthy

```bash
kubectl get nodes | grep <node-name>
# Expected: Ready
kubectl get pods --all-namespaces --field-selector spec.nodeName=<node-name> | grep -v Running
# Expected: empty
```

## Failure Signals

- Node goes NotReady again after kubelet restart
- New replacement node also goes NotReady (systemic issue)
- Pods won't reschedule (resource pressure cluster-wide)
- Drain hangs on PDB-protected pods

**If any failure signal is present:** Escalate.

## Rollback

1. **If you drained a node that recovered:** `kubectl uncordon <node-name>`
2. **If terminated wrong instance:** ASG launches replacement (no undo needed)

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Multiple nodes NotReady simultaneously | Platform team + EM | PagerDuty P1 | Immediate |
| Cannot restore node within 15 min | Platform team | #platform-support | 10 min |
| Cluster capacity insufficient after node loss | Platform team (scaling) | #platform-support | 15 min |
| Network partition affecting multiple nodes | Network/infra team | #platform-support | 5 min |

## Notes

- **Node NotReady doesn't immediately evict pods.** Default eviction timeout is 5 minutes. Pods remain until timeout.
- **Zombie pods** can occur after network partition heals. See [[INC-054-zombie-pods-node-network-partition]].
- **Clock skew** on a node can cause kubelet certificate validation failures. See [[INC-063-node-clock-skew-tls-failures]].
- **Always check if it's a single node or multiple** — multiple nodes = likely systemic (VPC, ASG, AZ issue).

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Cordon a staging node, stop kubelet, verify detection and drain procedures.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
