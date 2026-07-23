---
id: INC-015
title: Inode Exhaustion on App Server — Small File Accumulation
severity: SEV-2
service: notifications-service
environment: prod
category: degradation
date: 2026-03-21
duration: "42m"
detection_gap: "2m"
tags:
  - incident
  - disk
  - inode
  - infra
  - high
  - prod
  - monitoring
error_family: disk-full
resolution_runbook: RB-003
resolution_outcome: resolved
---

## Summary

At 08:45 UTC on 2026-03-21, notifications-service began failing to write temporary email template files to disk despite the data partition showing 67% free space. The underlying cause was inode exhaustion on `/var/lib/notifications/tmp` — the temp directory had accumulated 8.3 million zero-byte lock files left behind by a buggy template renderer introduced in v4.3.0. New files could not be created, causing all email rendering to fail with `ENOSPC: no space left on device` despite adequate block space.

## Symptoms

- PagerDuty: `NotificationsService-EmailRenderingFailed` at 08:47 UTC
- notifications-service logs: `ENOSPC: no space left on device — /var/lib/notifications/tmp`
- Email delivery failure rate: 100% for HTML emails (plaintext unaffected)
- `df -h /var/lib/notifications/tmp` reported 33% disk used — no block space issue
- `df -i /var/lib/notifications/tmp` reported 100% inodes used
- Sentry: spike of `IOException: Too many open files` errors

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All users expecting HTML email notifications (~14,200 over 42 min) |
| Services degraded | notifications-service (HTML email rendering fully failed) |
| Revenue impact | None directly — delayed transactional emails (order confirmations, password resets) |
| Duration | 08:45 → 09:27 UTC (42 min) |
| Data loss | None — failed emails queued and retried post-fix |
| SLA breach | No — email delivery SLA allows 1-hour delay |
| Customer comms | N/A — internal notification delay |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 08:45 | Email rendering began failing (inode exhaustion) |
| 08:47 | Alert fired: `NotificationsService-EmailRenderingFailed` |
| 08:48 | On-call acknowledged (Anika Petrov) |
| 08:55 | Root cause identified — inode exhaustion from orphaned lock files |
| 09:00 | Batch deletion of 8.3M zero-byte lock files started |
| 09:04 | Inodes freed; file creation restored |
| 09:10 | Notifications-service restarted |
| 09:20 | Hotfix v4.3.1 deployed with `finally` block fix |
| 09:27 | Email queue drained, incident closed |

## Diagnosis

1. Confirmed disk space was fine but inodes exhausted
   ```bash
   df -h /var/lib/notifications/tmp
   # 120G total, 80G free — block space fine
   df -i /var/lib/notifications/tmp
   # 8388608 inodes total, 8388607 used — 100%
   ```

2. Identified file count in temp directory
   ```bash
   ls /var/lib/notifications/tmp | wc -l
   # 8,312,440 files
   ```

3. Inspected file contents
   ```bash
   ls /var/lib/notifications/tmp | head -5
   # a1b2c3d4-lock  (zero-byte files, uuid named)
   find /var/lib/notifications/tmp -name "*.lock" -size 0 | wc -l
   # 8,311,220 — all zero-byte lock files
   ```

4. Traced to `TemplateRenderer.java` — `renderHtml()` created lock file before render, delete in `finally` block missing for exception path

5. Correlated with v4.3.0 deploy: 2026-03-18 09:00 UTC — files accumulating for 72 hours

## Resolution

1. **Mitigate:** Deleted all zero-byte lock files (batched to avoid fork bomb)
   ```bash
   find /var/lib/notifications/tmp -name "*.lock" -size 0 -print0 \
     | xargs -0 -P8 rm -f
   # ~8.3M files deleted in 4 minutes
   ```

2. **Fix:** Deployed hotfix v4.3.1 adding `finally { lockFile.delete(); }` to renderer
   ```bash
   kubectl rollout restart deployment/notifications-service -n notifications
   ```

3. **Verify:** Confirmed inodes freed and email rendering restored
   ```bash
   df -i /var/lib/notifications/tmp
   # 8388608 total, 91,234 used — 1%
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Email delivery at 0% for >10 min | Page on-call + EM | PagerDuty |
| Cannot clear inodes within 15 min | Engage infra — may require filesystem recreation | #platform-support |
| Inode issue spreading to other paths | Escalate to platform team immediately | #platform-support |

## Post-Incident Review

**What went well:**
- Root cause identified quickly from `df -i` — inode vs. block space distinction was clear
- Batch file deletion avoided overloading the filesystem

**What needs improvement:**
- No inode utilization monitoring existed
- Lock file cleanup not in exception path — missed in code review
- No max file count alert on temp directories

**Contributing factors (beyond root cause):**
- `TemplateRenderer.java` missing `finally` block for lock file cleanup on exception path
- High email volume from promotional campaign (4× normal) accelerated accumulation
- No periodic cleanup job for stale temp files

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Clear orphaned lock files, deploy hotfix v4.3.1 | Anika Petrov | 2026-03-21 | Done |
| Add inode utilization alert (>80%) on all app server filesystems | SRE team | 2026-04-04 | Open |
| Add cron: delete temp files older than 1 hour in notifications tmp dir | Anika Petrov | 2026-04-04 | Open |
| Add filesystem inode checks to production health dashboard | SRE team | 2026-04-04 | Open |

## Links

- Runbooks: [[RB-003-disk-space-full]]
- Related incidents: [[INC-005-disk-full-logs-node01]]
- PR/commit: v4.3.1 hotfix (finally block fix)
- Post-mortem doc: N/A
