---
id: INC-050
title: PVC Resize Stuck — Filesystem Not Expanded After Volume Resize
severity: SEV-2
service: postgres-primary
environment: prod
category: capacity
date: 2026-05-05
duration: "1h15m"
tags:
  - incident
  - kubernetes
  - pvc
  - storage
  - postgres
  - high
  - prod
---

## Summary

After expanding the PersistentVolumeClaim for postgres-primary from 200Gi to 500Gi, the underlying EBS volume was resized but the filesystem was not expanded. Kubernetes showed the PVC as `FileSystemResizePending` but the pod was not restarted to trigger the resize. Postgres continued writing to the 200Gi filesystem and hit disk full after 2 hours, causing a database outage.

## Symptoms

- PVC status: `FileSystemResizePending` for 2+ hours
- `df -h` inside pod still showing 200Gi
- Postgres eventually hit ENOSPC: `could not extend file "base/16384/...": No space left on device`
- All write operations failed

## Diagnosis

1. Checked PVC status
   ```bash
   kubectl get pvc postgres-data -n database -o yaml | grep -A5 "conditions"
   # type: FileSystemResizePending, status: True
   # message: "Waiting for user to (re-)start a pod to finish file system resize"
   ```

2. Pod never restarted — filesystem resize requires pod recreation
   ```bash
   kubectl get pod postgres-0 -n database -o jsonpath='{.status.startTime}'
   # Started 14 days ago — never restarted after PVC resize
   ```

3. Inside pod, filesystem still at old size
   ```bash
   kubectl exec postgres-0 -n database -- df -h /var/lib/postgresql
   # 200G total, 198G used (99%)
   ```

## Resolution

1. **Mitigate:** Deleted the pod to trigger filesystem expansion on restart
   ```bash
   kubectl delete pod postgres-0 -n database
   # StatefulSet recreates pod, kubelet expands filesystem on mount
   ```

2. **Verify:** Filesystem expanded
   ```bash
   kubectl exec postgres-0 -n database -- df -h /var/lib/postgresql
   # 500G total, 198G used (40%)
   ```

## Post-Incident Review

- PVC resize requires pod restart for filesystem expansion (by design)
- Added monitoring: alert if PVC condition is `FileSystemResizePending` for >10 minutes
- Added to runbook: after PVC resize, always restart the pod
- Scheduled proactive PVC resizes during maintenance windows with pod restart

## Links

- Runbooks: [[RB-003-disk-space-full]]
- Related incidents: [[INC-006-disk-full-db-volume]]
