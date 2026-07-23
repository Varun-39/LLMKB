---
id: INC-031
title: NFS Stale File Handle Causing Pod I/O Errors
severity: SEV-2
service: report-generator
environment: prod
category: degradation
date: 2026-03-19
duration: "55m"
tags:
  - incident
  - nfs
  - storage
  - kubernetes
  - stale-handle
  - io-error
error_family: unknown
resolution_runbook: RB-003
resolution_outcome: resolved
---

## Summary

The `report-generator` pods began failing with `Stale NFS file handle` errors after the NFS server (`nfs-prod-01`) was rebooted for kernel patching. The NFS export IDs changed on reboot, invalidating all existing file handles held by mounted clients. All report generation jobs failed for 55 minutes.

## Symptoms

- Application logs: `OSError: [Errno 116] Stale NFS file handle: '/mnt/reports/2026/Q1'`
- Kubernetes events: `Warning: FailedMount, Unable to attach or mount volumes`
- All 8 report-generator pods in `Error` state
- `df -h` on affected pods hung indefinitely
- NFS server was rebooted 20 minutes prior (maintenance window)

## Diagnosis

1. Confirmed stale handle from within a pod:
   ```bash
   kubectl exec -it report-gen-pod-0 -- ls /mnt/reports
   # ls: cannot access '/mnt/reports': Stale file handle
   ```
2. NFS server had been rebooted, changing the fsid of the export
3. Existing NFS mounts on all Kubernetes nodes held references to the old fsid
4. Kubernetes PV/PVC was still showing `Bound` (doesn't detect stale handles)

## Resolution

1. Unmounted stale NFS mounts on affected nodes:
   ```bash
   # On each worker node:
   umount -f /var/lib/kubelet/pods/*/volumes/kubernetes.io~nfs/report-storage
   ```
2. Deleted affected pods to force fresh mount:
   ```bash
   kubectl delete pods -l app=report-generator --force --grace-period=0
   ```
3. New pods mounted NFS cleanly with updated handles
4. Verified I/O working:
   ```bash
   kubectl exec -it report-gen-pod-0 -- ls /mnt/reports/2026/Q1
   ```

## Post-Incident Review

- NFS server reboots invalidate all client file handles — must restart NFS-dependent pods after server maintenance
- Added `fsid=0` to NFS export config to stabilize export IDs across reboots
- Added post-maintenance check: verify NFS mount health on all nodes
- Documented in runbook for NFS maintenance windows

## Links

- Related: [[RB-003-disk-space-full]]
