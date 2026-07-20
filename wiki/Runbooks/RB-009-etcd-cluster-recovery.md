---
id: RB-009
title: etcd Cluster Recovery and Leader Stabilization
service: kubernetes-control-plane
related_services:
  - kube-apiserver
  - kube-scheduler
  - kube-controller-manager
severity: SEV-1
environment: prod
category: resource-exhaustion
risk_level: high
estimated_duration: "25m"
approval_required: yes
approver_role: Platform Lead
tags:
  - runbook
  - etcd
  - kubernetes
  - control-plane
  - leader-election
  - prod
related_incidents:
  - "[[INC-044-etcd-leader-election-slow-disk]]"
  - "[[INC-004-k8s-node-notready]]"
related_runbooks:
  - "[[RB-007-pod-crash-investigation]]"
related_guardrails: []
---

## Purpose

Diagnose and recover from etcd cluster instability including leader election thrashing, member failures, and disk performance issues.

**Desired outcome:** Stable etcd cluster with consistent leader, fsync latency <10ms, and Kubernetes API server fully responsive.

## Success Criteria

- etcd leader stable for >10 minutes (no leader changes)
- `etcdctl endpoint health` returns healthy for all members
- etcd fsync P99 <10ms
- kube-apiserver responding to all requests without timeout
- No pending or stalled deployments in the cluster

## Scope

| Attribute | Value |
|-----------|-------|
| Service | kubernetes-control-plane (etcd) |
| Related services | kube-apiserver, kube-scheduler, kube-controller-manager |
| Environments | prod |
| Use when | `Etcd-LeaderChangesHigh`, `Etcd-HighFsync`, `APIServer-Timeout` alerts |
| Do NOT use when | API server issues are caused by webhook timeouts (see [[RB-006-failed-deployment-rollback]]) |
| Risk level | High (data loss possible if etcd corrupted) |
| Estimated duration | 20–25 minutes |
| Approval required | Yes — Platform Lead |

## Prerequisites

- [ ] SSH access to control plane nodes
- [ ] `etcdctl` installed with correct endpoints and certs
- [ ] etcd cluster topology known (3 or 5 members, IPs)
- [ ] Backup of etcd data directory verified within last 24h

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `etcdctl` | Cluster diagnostics and operations | etcd admin certs |
| SSH | Control plane node access | sudo |
| CloudWatch/Grafana | Disk I/O metrics | Read access |
| `kubectl` | API server health verification | Cluster admin |

## Trigger

- Alert: `Etcd-LeaderChangesHigh` (>3 leader changes in 10 min)
- Alert: `Etcd-HighFsyncLatency` (P99 >50ms)
- Symptom: kube-apiserver returning 504 or `etcdserver: request timed out`
- Symptom: `kubectl` commands hanging or timing out
- Metric: `etcd_disk_wal_fsync_duration_seconds` P99 >50ms

## Triage

1. Check etcd cluster health
   ```bash
   ETCDCTL_API=3 etcdctl --endpoints=https://etcd-0:2379,https://etcd-1:2379,https://etcd-2:2379 \
     --cacert=/etc/kubernetes/pki/etcd/ca.crt \
     --cert=/etc/kubernetes/pki/etcd/server.crt \
     --key=/etc/kubernetes/pki/etcd/server.key \
     endpoint health --cluster -w table
   # What to look for: any member unhealthy or slow
   ```

2. Check leader stability
   ```bash
   etcdctl endpoint status --cluster -w table
   # What to look for: IS LEADER column, RAFT TERM changing = unstable
   ```

3. Wrong symptoms? API server webhook issue? → Try [[RB-006-failed-deployment-rollback]]

## Investigation

1. **Check disk fsync latency**
   ```bash
   etcdctl check perf --load="s"
   # What to look for: PASS/FAIL on fsync latency (should be <10ms)
   ```

2. **Check for slow disk I/O on etcd node**
   ```bash
   ssh etcd-node-1
   iostat -x 1 5
   # What to look for: await >10ms, %util >80% on etcd volume
   ```

3. **Check etcd database size**
   ```bash
   etcdctl endpoint status --cluster -w table
   # What to look for: DB SIZE column — if >4GB, compaction needed
   ```

4. **Check for alarms**
   ```bash
   etcdctl alarm list
   # What to look for: NOSPACE alarm = DB hit quota
   ```

5. **Decision point:**
   - IF disk I/O slow → proceed to Mitigation Option A
   - IF DB size large (>4GB) → proceed to Mitigation Option B
   - IF single member failed → proceed to Mitigation Option C
   - IF NOSPACE alarm → proceed to Mitigation Option D
   - IF unclear → escalate (see Escalation section)

## Mitigation

### Option A: Disk I/O causing leader thrashing

```bash
# Move etcd data to faster volume (io2 with provisioned IOPS):
aws ec2 modify-volume --volume-id <vol-id> --volume-type io2 --iops 10000
# Restart etcd to pick up improved I/O:
systemctl restart etcd
```

### Option B: Database too large — compact and defragment

```bash
# Get current revision:
rev=$(etcdctl endpoint status -w json | jq '.[0].Status.header.revision')
# Compact:
etcdctl compact $rev
# Defragment all members:
etcdctl defrag --cluster
```

### Option C: Single member failed — rejoin

```bash
# Remove failed member:
etcdctl member remove <member-id>
# Re-add as new member:
etcdctl member add etcd-2 --peer-urls=https://etcd-2:2380
# Start etcd with --initial-cluster-state=existing
```

### Option D: NOSPACE alarm — free space and disarm

```bash
# Compact and defrag first (Option B), then:
etcdctl alarm disarm
```

**After mitigation:** Monitor for 10 minutes — leader stable, fsync <10ms, API server responsive.

## Verification

- [ ] `etcdctl endpoint health` healthy for all members
- [ ] Leader stable for 10+ minutes
- [ ] fsync P99 <10ms
- [ ] `kubectl get nodes` responds in <1s
- [ ] No stalled deployments or operations

```bash
etcdctl endpoint health --cluster -w table
etcdctl endpoint status --cluster -w table
kubectl get nodes
# Expected: all responsive, no timeouts
```

## Failure Signals

- Leader continues thrashing after disk upgrade
- Member cannot rejoin cluster (data corruption)
- DB size grows back rapidly after compaction
- API server still timing out despite healthy etcd

**If any failure signal is present:** Do NOT repeat. Proceed to Rollback or Escalation.

## Rollback

1. **If volume change caused issues:** Revert to previous volume type
2. **If member removal broke quorum:** Restore from etcd snapshot
   ```bash
   etcdctl snapshot restore /backup/etcd-snapshot.db --data-dir=/var/lib/etcd-restore
   ```
3. Notify #incident-response: "etcd recovery failed — escalating."

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Quorum lost (majority of members down) | Platform Lead + CTO | PagerDuty P1 | Immediate |
| Data corruption suspected | Platform team + backup team | #incident-response | 5 min |
| Cannot restore from snapshot | AWS support (if managed) | Support case | 15 min |
| Leader unstable >30 min despite mitigation | Senior platform engineer | Direct page | 5 min |

## Notes

- **Never defragment all members simultaneously.** Defrag one at a time to maintain availability.
- **etcd fsync latency is the #1 cause of leader thrashing.** Always check disk first.
- **etcd quota default is 2GB.** If approaching quota, compact immediately — NOSPACE alarm blocks all writes including kube-apiserver.
- **Snapshot before any destructive operation.** `etcdctl snapshot save /tmp/etcd-backup-$(date +%s).db`

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Simulate disk pressure on staging etcd node using stress-ng, verify leader failover and recovery.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Platform Team | Initial publication |
