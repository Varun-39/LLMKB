---
id: INC-005
title: Disk Full on Logging Node — /var/log Exhausted
severity: SEV-2
service: notifications-service
environment: prod
category: degradation
status: resolved
owner: Anika Petrov
assigned-to: Anika Petrov
date: 2026-05-15
duration: 28 minutes
created: 2026-05-15
updated: 2026-05-15
tags:
  - incident
  - disk
  - logging
  - high
  - prod
  - monitoring
related_runbooks:
  - "[[RB-002-disk-space-full]]"
related_incidents: []
---

# INC-005 — Disk Full on Logging Node: /var/log Exhausted

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

## Possible Causes

1. **Debug log level left enabled in prod** — deployed in v4.2.0, not reverted post-deploy
2. **Log rotation misconfigured** — logrotate not running on `/var/log/notifications/`
3. **Disk undersized** — log volume not expanded after recent traffic growth
4. **Runaway error loop** — repeated retry errors each generating a full stack trace

## Troubleshooting Steps

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

1. Truncated the runaway log file immediately
   ```bash
   truncate -s 0 /var/log/notifications/app.log
   ```

2. Changed log level to INFO via env var (dynamic — no restart needed)
   ```bash
   kubectl set env deployment/notifications-service -n notifications LOG_LEVEL=INFO
   ```

3. Confirmed disk freed and Fluentd resumed
   ```bash
   df -h /var/log   # 12G / 200G
   systemctl status fluentd  # Active: running
   ```

4. Created logrotate config for notifications
   ```
   /var/log/notifications/*.log {
     daily
     rotate 7
     compress
     missingok
     notifempty
     size 500M
   }
   ```

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Disk >95% and still growing | Page on-call immediately | PagerDuty |
| Alerting pipeline blind >15 min | Escalate to EM, switch to manual monitoring | #incident-response |
| Cannot free disk within 10 min | Engage infra team for volume expansion | #platform-support |

## Post-Incident Notes

**Went well:**
- `LogNode-DiskFull` alert fired before service disruption
- Dynamic log level change avoided a pod restart

**Improve:**
- Debug log level shipped to prod with no rollback plan
- No logrotate config existed for notifications-service
- No disk trend alert before hitting 100%

**Action items:**
- [x] Truncated log, set LOG_LEVEL=INFO
- [x] Created logrotate config
- [ ] Add release checklist item: verify LOG_LEVEL is INFO/WARN in prod configs
- [ ] Add Grafana alert: disk >80% on log-node-01
- [ ] Automate logrotate config deployment for all services via Ansible

## Related Runbooks

- [[RB-002-disk-space-full]]
