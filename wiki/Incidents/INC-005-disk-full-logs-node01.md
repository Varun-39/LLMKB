---
id: INC-005
title: Disk Full on Logging Node — /var/log Exhausted
severity: SEV-2
service: notifications-service
environment: prod
category: degradation
date: 2026-05-15
duration: "28m"
detection_gap: "2m"
tags:
  - incident
  - disk
  - logging
  - high
  - prod
  - monitoring
error_family: disk-full
resolution_runbook: RB-003
resolution_outcome: resolved
---

## Summary

The centralized logging node `log-node-01` reached 100% disk utilization on `/var/log` at 07:18 UTC on 2026-05-15 due to runaway debug logging from notifications-service. Log ingestion stopped for Fluentd, causing a 28-minute gap in observability across all prod services and triggering failures in log-dependent alerting pipelines.

## Symptoms

- PagerDuty: `LogNode-DiskFull` at 07:20 UTC
- Fluentd: `errno=ENOSPC — no space left on device` in Fluentd logs
- Kibana: log ingestion flatlined at 07:18 UTC
- APM alerts based on log patterns stopped firing
- notifications-service log file growing at ~420 MB/min (baseline: ~3 MB/min)

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | No direct user impact — observability gap |
| Services degraded | Log pipeline (down), alerting based on log patterns (blind) |
| Revenue impact | None directly; risk of missed alerts during gap |
| Duration | 07:18 → 07:46 UTC (28 min) |
| Data loss | ~28 min of logs not ingested (lost — not buffered to disk) |
| SLA breach | No — observability gap, no user-facing SLA impacted |
| Customer comms | N/A — internal observability issue |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 07:18 | Disk reached 100%, Fluentd ingestion stopped |
| 07:20 | Alert fired: `LogNode-DiskFull` |
| 07:21 | On-call acknowledged (Anika Petrov) |
| 07:28 | Root cause identified — debug logging from notifications-service |
| 07:32 | Log file truncated, disk freed |
| 07:35 | Log level changed to INFO via env var |
| 07:40 | Fluentd resumed ingestion |
| 07:46 | Logrotate config created, incident closed |

## Diagnosis

1. Confirmed disk full state
   ```bash
   df -h /var/log
   # /dev/xvdb  200G  200G  0  100% /var/log
   ```

2. Found the culprit directory
   ```bash
   du -sh /var/log/* | sort -rh | head -10
   # 195G  /var/log/notifications
   ```

3. Inspected log file growth rate
   ```bash
   watch -n5 'du -sh /var/log/notifications/app.log'
   # Growing ~420 MB per 5s
   ```

4. Tailed log file — all entries at DEBUG level
   ```bash
   tail -100 /var/log/notifications/app.log | grep level
   # Pattern: "DEBUG - Email render trace: ..." repeated every 2ms
   ```

5. Correlated with notifications-service deploy — v4.2.0 deployed 2026-05-14 23:30 UTC

6. Confirmed logrotate not configured for this directory
   ```bash
   ls /etc/logrotate.d/notifications
   # No such file
   ```

## Resolution

1. **Mitigate:** Truncated the runaway log file immediately
   ```bash
   truncate -s 0 /var/log/notifications/app.log
   ```

2. **Fix:** Changed log level to INFO via env var (dynamic — no restart needed)
   ```bash
   kubectl set env deployment/notifications-service -n notifications LOG_LEVEL=INFO
   ```

3. **Verify:** Confirmed disk freed and Fluentd resumed
   ```bash
   df -h /var/log   # 12G / 200G
   systemctl status fluentd  # Active: running
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Disk >95% and still growing | Page on-call immediately | PagerDuty |
| Alerting pipeline blind >15 min | Escalate to EM, switch to manual monitoring | #incident-response |
| Cannot free disk within 10 min | Engage infra team for volume expansion | #platform-support |

## Post-Incident Review

**What went well:**
- `LogNode-DiskFull` alert fired before service disruption
- Dynamic log level change avoided a pod restart

**What needs improvement:**
- Debug log level shipped to prod with no rollback plan
- No logrotate config existed for notifications-service
- No disk trend alert before hitting 100%

**Contributing factors (beyond root cause):**
- v4.2.0 deployed with LOG_LEVEL=DEBUG in prod config
- No deployment checklist item to verify log levels
- Missing logrotate for the notifications log directory

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Truncate log, set LOG_LEVEL=INFO | Anika Petrov | 2026-05-15 | Done |
| Create logrotate config for notifications | Anika Petrov | 2026-05-15 | Done |
| Add release checklist item: verify LOG_LEVEL is INFO/WARN in prod | Platform team | 2026-05-29 | Open |
| Add Grafana alert: disk >80% on log-node-01 | SRE team | 2026-05-29 | Open |
| Automate logrotate config deployment for all services via Ansible | Platform team | 2026-06-05 | Open |

## Links

- Runbooks: [[RB-003-disk-space-full]]
- Related incidents: [[INC-014-k8s-node-disk-pressure]]
- PR/commit: N/A
- Post-mortem doc: N/A
