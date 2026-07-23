---
id: INC-062
title: Helm Release Secret Exceeded 1MB — Upgrades Blocked
severity: SEV-3
service: reporting-service
environment: prod
category: deployment-failure
date: 2026-06-03
duration: "1h"
tags:
  - incident
  - helm
  - kubernetes
  - secret
  - etcd
  - deployment
  - moderate
  - prod
error_family: unknown
resolution_runbook: RB-006
resolution_outcome: resolved
---

## Summary

The reporting-service Helm release accumulated 45 revisions of release history, and the consolidated Helm release secret exceeded etcd's 1MB value size limit. All `helm upgrade` commands failed with `etcdserver: request is too large`. The service could not be deployed or rolled back via Helm for 1 hour until release history was pruned.

## Symptoms

- CI/CD pipeline failure: `Error: UPGRADE FAILED: etcdserver: request is too large`
- Helm: `helm history reporting-service -n reporting` showing 45 revisions
- No user impact (existing pods running), but deployment completely blocked

## Diagnosis

1. Confirmed etcd size limit hit
   ```bash
   helm upgrade reporting-service ./chart -n reporting --dry-run
   # Error: UPGRADE FAILED: etcdserver: request is too large
   ```

2. Checked release history size
   ```bash
   kubectl get secret -n reporting -l owner=helm | wc -l
   # 45 secrets (one per revision)
   helm history reporting-service -n reporting | wc -l
   # 45 revisions
   ```

3. Each revision storing full manifest (including large ConfigMaps for report templates)

## Resolution

1. **Mitigate:** Pruned old Helm release secrets
   ```bash
   # Deleted revisions 1-35 manually:
   kubectl delete secret sh.helm.release.v1.reporting-service.v1 -n reporting
   # ... through v35
   ```

2. **Fix:** Set `--history-max 10` in all Helm upgrade commands in CI

3. **Verify:** `helm upgrade` succeeded after pruning

## Post-Incident Review

- Helm stores full manifest in each revision secret (can be large)
- Set `--history-max 10` globally in all CI/CD Helm commands
- Moved large report templates from ConfigMap to S3 (reduces manifest size)
- Added CI check: fail if Helm release has >15 revisions

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]]
- Related incidents: [[INC-029-argocd-sync-loop-crd-mismatch]]
