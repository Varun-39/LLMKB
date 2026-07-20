---
id: INC-071
title: Kubernetes API Server Audit Log Filled Control Plane Disk
severity: SEV-1
service: kubernetes-control-plane
environment: prod
category: outage
date: 2026-06-19
duration: "15m"
tags:
  - incident
  - kubernetes
  - audit-log
  - disk
  - control-plane
  - critical
  - prod
---

## Summary

The Kubernetes API server audit log grew to 50GB and filled the control plane node's disk (60GB volume). The API server became unable to write responses, causing all kubectl commands, deployments, and scaling operations to fail. Pods continued running but no new scheduling or cluster management was possible for 15 minutes.

## Symptoms

- kubectl: `error: the server is currently unable to handle the request`
- API server logs: `write: no space left on device`
- Control plane node disk: 100%
- All deployments, scaling, and pod scheduling frozen
- Existing pods unaffected (already scheduled)

## Diagnosis

1. Confirmed control plane disk full
   ```bash
   ssh admin@control-plane-1
   df -h /
   # 60G 60G 0 100% /
   du -sh /var/log/kubernetes/audit/* | sort -rh | head -3
   # 48G /var/log/kubernetes/audit/audit.log
   ```

2. Audit log rotation not configured (log grew unbounded)
   ```bash
   cat /etc/kubernetes/manifests/kube-apiserver.yaml | grep audit
   # --audit-log-path=/var/log/kubernetes/audit/audit.log
   # No --audit-log-maxsize or --audit-log-maxage flags
   ```

## Resolution

1. **Mitigate:** Truncated audit log
   ```bash
   truncate -s 0 /var/log/kubernetes/audit/audit.log
   ```

2. **Fix:** Added audit log rotation flags to API server manifest
   ```bash
   # Added: --audit-log-maxsize=500 --audit-log-maxbackup=3 --audit-log-maxage=7
   ```

3. **Verify:** API server responsive, disk at 15%

## Post-Incident Review

- Audit logging enabled without rotation is a ticking bomb
- Added maxsize=500MB, maxbackup=3, maxage=7 days
- Added control plane disk usage alert at 70%
- Considered shipping audit logs to external sink instead of local disk

## Links

- Runbooks: [[RB-003-disk-space-full]]
- Related incidents: [[INC-005-disk-full-logs-node01]]
