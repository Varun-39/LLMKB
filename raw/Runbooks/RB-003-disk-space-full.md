<!-- File: RB-003-disk-space-full.md -->
---
id: RB-003
title: Disk Space Full on Critical Node or Volume
service_scope: all services
environment_scope: prod, staging
owner: SRE Team
severity_scope: high, critical
tags:
  - runbook
  - disk
  - infra
  - inode
  - storage
  - prod
created: 2026-06-02
updated: 2026-06-02
related_incidents:
  - "[[INC-005-disk-full-logs-node01]]"
  - "[[INC-006-disk-full-db-volume]]"
  - "[[INC-014-k8s-node-disk-pressure]]"
  - "[[INC-015-inode-exhaustion-var-log]]"
---

# Disk Space Full on Critical Node or Volume

## Trigger

- PagerDuty alert: `*-DiskFull`, `*-DiskPressure`, or `*-InodeExhaustion`
- Kubernetes node condition: `DiskPressure: True`
- Application errors: `ENOSPC: no space left on device`
- Postgres/MySQL errors: `could not extend file ... No space left on device`
- Fluentd/logging pipeline: `errno=ENOSPC`

**Desired outcome:** Disk utilization below 70%, no ENOSPC errors, all services writing normally.

## Preconditions

- [ ] SSH access to affected node or `kubectl exec` into affected pod
- [ ] `sudo` access for filesystem operations if on bare-metal/VM
- [ ] Knowledge of which volume/partition is full (from alert payload)
- [ ] For DB volumes: confirm whether dropping data requires DBA approval

**Required tools:** SSH, kubectl, df, du, find, lsof, truncate, AWS Console (for EBS expansion)

## Commands and Checks

### 1. Identify which filesystem is full

```bash
df -h
# Look for any filesystem at >90% usage
df -i
# Check inodes — if inodes at 100% but blocks free, this is inode exhaustion
```

### 2. Find largest consumers

```bash
du -sh /* | sort -rh | head -10
# Drill down into the largest directory:
du -sh /var/log/* | sort -rh | head -10
du -sh /var/lib/docker/containers/* | sort -rh | head -5
```

### 3. Check if inode exhaustion (block space OK but writes failing)

```bash
df -i /var/log
# IF inodes at 100%:
find /var/log -type f -size 0 | wc -l
# Large number of zero-byte files = likely orphaned lock/temp files
find /path/to/suspect -name "*.lock" -o -name "*.tmp" | wc -l
```

### 4. Check for open file handles holding deleted files

```bash
lsof +L1 | head -20
# Files that are deleted but still held open by a process won't free space until process closes them
# Note the PID and size of any large deleted-but-open files
```

### 5. For Kubernetes nodes — check ephemeral storage

```bash
kubectl describe node <node-name> | grep -A10 "Conditions"
# Look for: DiskPressure: True
kubectl describe node <node-name> | grep -A5 "Allocated resources"
# Check ephemeral-storage requests vs. capacity
```

### 6. For database volumes specifically

```bash
# On the DB host:
du -sh /var/lib/postgresql/*/main/pg_wal/
# Check WAL accumulation
psql -U postgres -c "SELECT slot_name, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag FROM pg_replication_slots;"
# Large lag = WAL not being cleaned up
```

## Mitigation

### Scenario A: Log files consuming disk

```bash
# Truncate (not delete) the large log file to free space immediately:
truncate -s 0 /var/log/<service>/app.log

# If log level is DEBUG in prod, fix it:
kubectl set env deployment/<service> -n <namespace> LOG_LEVEL=INFO
# Or on bare metal:
systemctl restart <service>
```

### Scenario B: Container logs on Kubernetes node

```bash
# Find and truncate the largest container log:
truncate -s 0 /var/lib/docker/containers/<container-id>/*-json.log
```

### Scenario C: Inode exhaustion (millions of small files)

```bash
# Delete in batches to avoid overloading filesystem:
find /path/to/dir -name "*.lock" -size 0 -print0 | xargs -0 -P4 rm -f
# Verify inodes freed:
df -i /path/to/dir
```

### Scenario D: Database volume — WAL accumulation

```bash
# Check for lagging replication slots:
psql -U postgres -c "SELECT * FROM pg_replication_slots;"
# Drop stale slot if replica is decommissioned:
psql -U postgres -c "SELECT pg_drop_replication_slot('<slot-name>');"
# Run VACUUM on bloated tables:
psql -U postgres -d <db> -c "VACUUM (VERBOSE) <table>;"
```

### Scenario E: Volume needs permanent expansion (AWS EBS)

```bash
# In AWS Console: modify volume size (online, no downtime)
# Then on the instance:
sudo growpart /dev/xvdf 1
sudo resize2fs /dev/xvdf1   # ext4
# or: sudo xfs_growfs /      # xfs
df -h  # confirm new size
```

## Verification

- [ ] `df -h` shows affected filesystem below 70%
- [ ] `df -i` shows inodes below 80% (if inode issue)
- [ ] No `ENOSPC` errors in application/database logs for 10 minutes
- [ ] Kubernetes node DiskPressure taint removed (if applicable)
- [ ] Services writing to disk successfully (test write + health check)

```bash
df -h <mount-point>
df -i <mount-point>
kubectl get nodes  # confirm no DiskPressure taint
kubectl logs -l app=<service> -n <namespace> --tail=20 | grep -i "ENOSPC\|no space"
# Expect: no results
```

## Rollback

Most disk cleanup actions are not reversible (deleted files are gone). Safeguards:

- If you truncated a log file: no rollback needed, logs will regenerate
- If you dropped a replication slot: recreate it once the replica is healthy again
  ```bash
  psql -U postgres -c "SELECT pg_create_physical_replication_slot('<slot-name>');"
  ```
- If you expanded a volume: volumes cannot be shrunk — this is permanent (but safe)
- If you accidentally deleted data files: initiate restore from backup immediately and escalate

## Escalation

| Condition | Escalate to | Channel |
|-----------|-------------|---------|
| Cannot free sufficient space within 15 min | Platform/infra team | #platform-support |
| Database volume full with active writes failing | DBA team + EM | PagerDuty P1 |
| Need to expand EBS volume beyond approved size | Manager approval required | #incident-response |
| Data accidentally deleted | Immediately escalate to DBA for backup restore | #data-eng |

## Notes / Gotchas

- **Always check inodes AND blocks.** `df -h` can show free space while `df -i` is at 100%. See [[INC-015-inode-exhaustion-var-log]] for a real example.
- **Truncate, don't delete log files** if a process still holds them open. `rm` won't free space until the file handle is closed; `truncate -s 0` frees space immediately.
- **Replication slot lag is the #1 cause of Postgres WAL accumulation.** See [[INC-006-disk-full-db-volume]] — 191 GB WAL retained by a single lagging slot.
- **Docker daemon log rotation:** If container logs are the culprit, add `"log-opts": {"max-size": "100m", "max-file": "3"}` to Docker daemon config as a permanent fix.
- **Ephemeral storage on K8s nodes:** Add `ephemeral-storage` limits to pod specs to prevent any single pod from filling the node. See [[INC-014-k8s-node-disk-pressure]].
