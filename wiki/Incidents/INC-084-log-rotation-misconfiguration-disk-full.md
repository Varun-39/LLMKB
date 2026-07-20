---
id: INC-084
title: Log Rotation Misconfiguration Filled /var/log Partition
severity: SEV-2
service: general
environment: prod
category: outage
date: 2026-04-09
duration: "55m"
tags:
  - incident
  - disk
  - logrotate
  - logging
  - partition
  - prod
  - infrastructure
---

## Summary

A logrotate configuration deployed during a logging overhaul omitted the `compress` and `maxsize` directives for three high-volume application log files. Over 72 hours, uncompressed, uncapped logs grew to fill the `/var/log` partition on worker-node-02, causing kubelet and systemd journal writes to fail and ultimately forcing the node into a `DiskPressure` condition.

## Symptoms

- `kubectl get node worker-node-02`: condition `DiskPressure=True`
- kubelet logs: `failed to write: no space left on device`
- `/var/log` partition: 100% utilised (df -h)
- Three log files each >8 GB: `app-api.log`, `app-worker.log`, `app-scheduler.log`
- Pods on node-02 began eviction

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~600 (sessions routed away from node-02 pods) |
| Services degraded | api-gateway, worker processes (node-02 pods evicted) |
| Revenue impact | Minimal — traffic redistributed |
| Duration | 07:10 → 08:05 UTC (55 min) |
| Data loss | None |
| SLA breach | No |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 04:30 | logrotate cron ran; misconfigured files skipped rotation |
| 07:10 | `/var/log` partition hits 100%; DiskPressure condition fires |
| 07:15 | Pods begin eviction on node-02 |
| 07:20 | On-call paged |
| 07:35 | Root cause identified (logrotate config) |
| 08:05 | Disk cleared, node returned to Ready |

## Diagnosis

1. Confirmed disk full:
   ```bash
   df -h /var/log
   # /dev/sdb1  50G  50G  0 100% /var/log
   ```
2. Found oversized log files:
   ```bash
   du -sh /var/log/app/* | sort -rh | head -5
   # 8.4G app-api.log
   # 8.1G app-worker.log
   # 7.9G app-scheduler.log
   ```
3. Checked logrotate config:
   ```bash
   cat /etc/logrotate.d/app
   # /var/log/app/*.log { daily rotate 7 missingok notifempty }
   # Missing: compress, maxsize, copytruncate
   ```
4. Confirmed last rotation was 4 days ago (before the bad config was deployed).

## Resolution

1. **Mitigate:** Truncated the three largest log files to free space
   ```bash
   truncate -s 0 /var/log/app/app-api.log
   truncate -s 0 /var/log/app/app-worker.log
   truncate -s 0 /var/log/app/app-scheduler.log
   ```
2. **Fixed logrotate config:**
   ```bash
   cat > /etc/logrotate.d/app << 'EOF'
   /var/log/app/*.log {
     daily
     rotate 7
     compress
     delaycompress
     maxsize 512M
     missingok
     notifempty
     copytruncate
   }
   EOF
   ```
3. **Forced rotation immediately:**
   ```bash
   logrotate -f /etc/logrotate.d/app
   ```
4. **Node DiskPressure cleared** after disk usage fell to 38%
5. **Verify:**
   ```bash
   kubectl get node worker-node-02
   # Ready, DiskPressure=False
   ```

## Post-Incident Review

**What went well:**
- DiskPressure alert fired quickly; on-call responded within 10 minutes

**What needs improvement:**
- No CI test for logrotate configuration correctness
- 72-hour window before detection is too long

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add logrotate config lint step to infra CI pipeline | Platform | 2026-04-20 | Open |
| Add disk usage alert at 75% threshold (current is 90%) | Observability | 2026-04-14 | Open |
| Audit all logrotate configs across all nodes | SRE | 2026-04-14 | Open |

## Links

- Runbooks: [[RB-003-disk-space-full]]
- Related incidents: [[INC-005-disk-full-logs-node01]], [[INC-006-disk-full-db-volume]]
