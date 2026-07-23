---
id: INC-029
title: ArgoCD Sync Loop Due to CRD Version Mismatch
severity: SEV-3
service: argocd
environment: prod
category: configuration
date: 2026-03-08
duration: "1h40m"
tags:
  - incident
  - argocd
  - gitops
  - crd
  - sync-loop
  - kubernetes
error_family: high-cpu
resolution_runbook: RB-031
resolution_outcome: resolved
---

## Summary

ArgoCD entered a continuous sync loop on 12 applications after a Helm chart update introduced a CRD with `apiVersion: v1beta2` while the cluster still had `v1beta1` installed. ArgoCD detected drift on every sync (the server normalized to v1beta1), re-applied v1beta2, server normalized again — infinite loop. CPU on ArgoCD repo-server spiked to 95%.

## Symptoms

- ArgoCD UI: 12 applications showing `OutOfSync` → `Syncing` → `OutOfSync` repeatedly
- argocd-repo-server CPU at 95% (constant manifest rendering)
- `argocd app diff` showed changes on every check despite identical desired state
- Kubernetes audit log showed rapid repeated `PATCH` operations on the same resources
- Alert: `ArgoCD-SyncRetryExhausted` on multiple apps

## Diagnosis

1. Ran diff on one affected app:
   ```bash
   argocd app diff order-service --local ./charts/order-service
   ```
2. Diff showed `apiVersion: autoscaling/v1beta2` in Git vs `apiVersion: autoscaling/v1beta1` returned by API server
3. The API server was auto-converting the resource to the stored version (v1beta1) on GET
4. ArgoCD saw this as drift and re-applied, creating the loop
5. Helm chart was updated to reference v1beta2 but the CRD was never upgraded on the cluster

## Resolution

1. Applied the updated CRD to the cluster:
   ```bash
   kubectl apply -f https://raw.githubusercontent.com/.../autoscaling-v1beta2-crd.yaml
   ```
2. Triggered a hard refresh on affected ArgoCD apps:
   ```bash
   argocd app get order-service --hard-refresh
   ```
3. Verified sync status stabilized to `Synced`
4. Confirmed repo-server CPU dropped to normal

## Post-Incident Review

- CRD upgrades must happen BEFORE Helm chart updates that reference new versions
- Added ArgoCD resource exclusion for CRDs (managed separately via a dedicated CRD-management app)
- Added CI check: if chart references a CRD version, verify it exists in target cluster
- Documented CRD upgrade ordering in deployment guide

## Links

- Related: [[RB-031-ci-cd-pipeline-failure]]
