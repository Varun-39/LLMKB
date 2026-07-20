---
id: RB-003
title: Disk Space Full on Critical Node or Volume
service: "*"
related_services:
  - postgres-primary
  - fluentd
  - docker-daemon
severity: SEV-2
environment: prod
category: resource-exhaustion
risk_level: high
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - disk
  - infra
  - inode
  - storage
  - prod
related_incidents:
  - "[[INC-005-disk-full-logs-node01]]"
  - "[[INC-006-disk-full-db-volume]]"
  - "[[INC-014-k8s-node-disk-pressure]]"
  - "[[INC-015-inode-exhaustion-var-log]]"
related_runbooks:
  - "[[RB-007-pod-crash-investigation]]"
related_guardrails: []
---

## Purpose

Diagnose and resolve disk space exhaustion (block or inode) on Kubernetes nodes, database volumes, or application log directories.

**Desired outcome:** Disk utilization below 70%, no ENOSPC errors, all services writing normally.

## Success Criteria

Before closing the incident or declaring the runbook complete, ALL of the following must be true:

- `df -h` shows affected filesystem below 70% usage
- `df -i` shows inodes below 80% (if inode issue)
- No `ENOSPC` errors in application or database logs for 10 minutes
- Kubernetes node DiskPressure taint removed (if applicable)
- Services writing to disk successfully confirmed via health check

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any service affected by disk full condition |
| Related services | postgres-primary, fluentd, docker-daemon |
| Environments | prod, staging |
| Use when | `*-DiskFull`, `*-DiskPressure`, `*-InodeExhaustion` alert, or ENOSPC errors |
| Do NOT use when | Issue is network-attached storage latency (not capacity) |
| Risk level | High (data loss possible if wrong files deleted) |
| Estimated duration | 15–20 minutes |
| Approval required | No (unless expanding EBS beyond approved size) |

## Prerequisites

- [ ] SSH access to affected node or `kubectl exec` into affected pod
- [ ] `sudo` access for filesystem operations if on bare-metal/VM
- [ ] Knowledge of which volume/partition is full (from alert payload)
- [ ] For DB volumes: DBA approval before dropping data or replication slots

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| SSH | Node-level filesystem operations | sudo access |
| `kubectl` | Pod/node inspection | Cluster admin |
| `df`, `du`, `find`, `lsof` | Disk diagnostics | Shell access |
| `truncate` | Safe log file cleanup | sudo access |
| AWS Console | EBS volume expansion | IAM write access |
| `psql` | Database WAL diagnostics | Superuser |

## Trigger

- Alert: `*-DiskFull`, `*-DiskPressure`, or `*-InodeExhaustion`
- Symptom: Kubernetes node condition `DiskPressure: True`
- Symptom: Application errors `ENOSPC: no space left on device`
- Symptom: Postgres/MySQL errors `could not extend file ... No space left on device`
- Symptom: Fluentd/logging pipeline `errno=ENOSPC`

## Triage

1. Identify which filesystem is full
   ```bash
   df -h
   # What to look for: any filesystem at >90% usage
   df -i
   # What to look for: inodes at 100% = inode exhaustion (blocks may be free)
   ```

2. Assess blast radius — single volume or multiple nodes
   ```bash
   kubectl get nodes -o wide
   kubectl describe node <node-name> | grep -A10 "Conditions"
   # What to look for: DiskPressure: True
   ```

3. Wrong symptoms? Not disk-related? → Try [[RB-007-pod-crash-investigation]]

## Investigation

1. **Find largest consumers**
   ```bash
   du -sh /* | sort -rh | head -10
   du -sh /var/log/* | sort -rh | head -10
   du -sh /var/lib/docker/containers/* | sort -rh | head -5
   ```

2. **Check if inode exhaustion** (block space OK but writes failing)
   ```bash
   df -i /var/log
   find /var/log -type f -size 0 | wc -l
   # What to look for: large number of zero-byte files = orphaned lock/temp files
   ```

3. **Check for open file handles holding deleted files**
   ```bash
   lsof +L1 | head -20
   # What to look for: files deleted but still held open — won't free space until process closes them
   ```

4. **For Kubernetes nodes — check ephemeral storage**
   ```bash
   kubectl describe node <node-name> | grep -A5 "Allocated resources"
   # What to look for: ephemeral-storage requests vs. capacity
   ```

5. **For database volumes — check WAL accumulation**
   ```bash
   du -sh /var/lib/postgresql/*/main/pg_wal/
   psql -U postgres -c "SELECT slot_name, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag FROM pg_replication_slots;"
   # What to look for: large lag = WAL not being cleaned up
   ```

6. **Decision point:**
   - IF log files consuming disk → proceed to Mitigation Option A
   - IF container logs on K8s node → proceed to Mitigation Option B
   - IF inode exhaustion → proceed to Mitigation Option C
   - IF database WAL accumulation → proceed to Mitigation Option D
   - IF volume needs permanent expansion → proceed to Mitigation Option E
   - IF unclear → escalate (see Escalation section)

## Mitigation

### Option A: Log files consuming disk

```bash
# Truncate (not delete) the large log file to free space immediately:
truncate -s 0 /var/log/<service>/app.log
# If log level is DEBUG in prod, fix it:
kubectl set env deployment/<service> -n <namespace> LOG_LEVEL=INFO
```

### Option B: Container logs on Kubernetes node

```bash
# Find and truncate the largest container log:
truncate -s 0 /var/lib/docker/containers/<container-id>/*-json.log
```

### Option C: Inode exhaustion (millions of small files)

```bash
# Delete in batches to avoid overloading filesystem:
find /path/to/dir -name "*.lock" -size 0 -print0 | xargs -0 -P4 rm -f
# Verify inodes freed:
df -i /path/to/dir
```

### Option D: Database volume — WAL accumulation

```bash
# Check for lagging replication slots:
psql -U postgres -c "SELECT * FROM pg_replication_slots;"
# Drop stale slot if replica is decommissioned:
psql -U postgres -c "SELECT pg_drop_replication_slot('<slot-name>');"
# Run VACUUM on bloated tables:
psql -U postgres -d <db> -c "VACUUM (VERBOSE) <table>;"
```

### Option E: Volume needs permanent expansion (AWS EBS)

```bash
# In AWS Console: modify volume size (online, no downtime)
# Then on the instance:
sudo growpart /dev/xvdf 1
sudo resize2fs /dev/xvdf1   # ext4
# or: sudo xfs_growfs /      # xfs
df -h  # confirm new size
```

**After mitigation:** Monitor for 10 minutes — confirm no new ENOSPC errors and disk usage remains below 70%.

## Verification

- [ ] `df -h` shows affected filesystem below 70%
- [ ] `df -i` shows inodes below 80% (if inode issue)
- [ ] No `ENOSPC` errors in application/database logs for 10 minutes
- [ ] Kubernetes node DiskPressure taint removed (if applicable)
- [ ] Services writing to disk successfully

```bash
df -h <mount-point>
df -i <mount-point>
kubectl get nodes  # confirm no DiskPressure taint
kubectl logs -l app=<service> -n <namespace> --tail=20 | grep -i "ENOSPC\|no space"
# Expected: no results
```

## Failure Signals

If the mitigation did NOT work, you will observe one or more of the following:

- Disk usage climbs back to >90% within minutes of cleanup
- New ENOSPC errors continue appearing in logs
- DiskPressure taint reappears on the node
- Database still unable to write (WAL not freed)
- Pods still being evicted due to ephemeral storage pressure

**If any failure signal is present after mitigation:** Do NOT repeat the same step. Proceed to Rollback or Escalation immediately.

## Rollback

Most disk cleanup actions are not reversible (deleted files are gone). Safeguards:

1. **If you truncated a log file:** No rollback needed — logs will regenerate.
2. **If you dropped a replication slot:** Recreate once the replica is healthy:
   ```bash
   psql -U postgres -c "SELECT pg_create_physical_replication_slot('<slot-name>');"
   ```
3. **If you expanded a volume:** Volumes cannot be shrunk — this is permanent (but safe).
4. **If you accidentally deleted data files:** Initiate restore from backup immediately and escalate.

5. Notify #incident-response: "Rollback executed — escalating."

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Cannot free sufficient space within 15 min | Platform/infra team | #platform-support | 10 min response |
| Database volume full with active writes failing | DBA team + EM | PagerDuty P1 | Immediate |
| Need to expand EBS volume beyond approved size | Manager approval | #incident-response | 5 min response |
| Data accidentally deleted | DBA for backup restore | #data-eng | Immediate |

## Notes

- **Always check inodes AND blocks.** `df -h` can show free space while `df -i` is at 100%. See [[INC-015-inode-exhaustion-var-log]].
- **Truncate, don't delete log files** if a process still holds them open. `rm` won't free space until the file handle is closed; `truncate -s 0` frees space immediately.
- **Replication slot lag is the #1 cause of Postgres WAL accumulation.** See [[INC-006-disk-full-db-volume]] — 191 GB WAL retained by a single lagging slot.
- **Docker daemon log rotation:** If container logs are the culprit, add `"log-opts": {"max-size": "100m", "max-file": "3"}` to Docker daemon config as a permanent fix.
- **Ephemeral storage on K8s nodes:** Add `ephemeral-storage` limits to pod specs to prevent any single pod from filling the node. See [[INC-014-k8s-node-disk-pressure]].
- See also: [[INC-005-disk-full-logs-node01]], [[INC-006-disk-full-db-volume]]

## Maintenance

- **Last tested:** 2026-06-02
- **Review cycle:** Quarterly
- **Next review:** 2026-09-02
- **Test method:** Fill a staging volume to 95% using `fallocate`, execute runbook cleanup steps, verify recovery.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-02 | SRE Team | Initial publication |
| 2026-06-12 | SRE Team | Migrated to new runbook template format |
