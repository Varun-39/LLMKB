---
id: INC-015
title: Inode Exhaustion on App Server — Small File Accumulation
severity: SEV-2
service: notifications-service
environment: prod
category: degradation
status: resolved
owner: Anika Petrov
assigned-to: Anika Petrov
date: 2026-03-21
duration: 42 minutes
created: 2026-03-21
updated: 2026-03-21
tags:
  - incident
  - disk
  - inode
  - infra
  - high
  - prod
  - monitoring
related_runbooks:
  - "[[RB-002-disk-space-full]]"
related_incidents:
  - "[[INC-005-disk-full-logs-node01]]"
---

# INC-015 — Inode Exhaustion on App Server: Small File Accumulation

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

## Possible Causes

1. **Orphaned lock files** — template renderer created `<uuid>.lock` files per render and deleted them only on successful completion, not on exception paths
2. **High email volume** — v4.3.0 deployed alongside a promotional campaign increasing email volume 4×
3. **tmp directory not monitored** — no inode or file-count alert on this path
4. **No cleanup job** — no periodic sweep of stale temp files older than 1 hour

## Troubleshooting Steps

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

1. Deleted all zero-byte lock files (batched to avoid fork bomb)
   ```bash
   find /var/lib/notifications/tmp -name "*.lock" -size 0 -print0 \
     | xargs -0 -P8 rm -f
   # ~8.3M files deleted in 4 minutes
   ```

2. Confirmed inodes freed
   ```bash
   df -i /var/lib/notifications/tmp
   # 8388608 total, 91,234 used — 1%
   ```

3. Restarted notifications-service to clear any held file handles
   ```bash
   kubectl rollout restart deployment/notifications-service -n notifications
   ```

4. Deployed hotfix v4.3.1 adding `finally { lockFile.delete(); }` to renderer

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Email delivery at 0% for >10 min | Page on-call + EM | PagerDuty |
| Cannot clear inodes within 15 min | Engage infra — may require filesystem recreation | #platform-support |
| Inode issue spreading to other paths | Escalate to platform team immediately | #platform-support |

## Post-Incident Notes

**Went well:**
- Root cause identified quickly from `df -i` — inode vs. block space distinction was clear
- Batch file deletion avoided overloading the filesystem

**Improve:**
- No inode utilization monitoring existed
- Lock file cleanup not in exception path — missed in code review
- No max file count alert on temp directories

**Action items:**
- [x] Cleared orphaned lock files, deployed hotfix v4.3.1
- [ ] Add inode utilization alert (>80%) on all app server filesystems
- [ ] Add cron: delete temp files older than 1 hour in notifications tmp dir
- [ ] Add filesystem inode checks to production health dashboard

## Related Runbooks

- [[RB-002-disk-space-full]]
