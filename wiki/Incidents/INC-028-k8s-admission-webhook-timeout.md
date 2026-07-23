---
id: INC-028
title: Kubernetes Admission Webhook Timeout Blocking All Deployments
severity: SEV-1
service: platform
environment: prod
category: outage
date: 2026-03-02
duration: "28m"
tags:
  - incident
  - kubernetes
  - webhook
  - admission-controller
  - deployments
  - critical
error_family: crashloopbackoff
resolution_runbook: RB-006
resolution_outcome: resolved
---

## Summary

A ValidatingAdmissionWebhook (`policy-enforcer`) became unreachable after its backing pod crashed due to an unhandled panic. All `kubectl apply`, Helm installs, and ArgoCD syncs were blocked with `context deadline exceeded` errors for 28 minutes. No workloads could be created or updated cluster-wide.

## Symptoms

- All deployments failing: `Error from server (InternalError): Internal error occurred: failed calling webhook "validate.policy-enforcer.io": context deadline exceeded`
- ArgoCD: all applications stuck in `Progressing` with sync errors
- Helm: `Error: UPGRADE FAILED: timed out waiting for the condition`
- `kubectl get pods -n policy-system` showed policy-enforcer pod in CrashLoopBackOff
- Pod logs: `panic: runtime error: invalid memory address or nil pointer dereference`

## Diagnosis

1. Identified the blocking webhook:
   ```bash
   kubectl get validatingwebhookconfigurations
   # policy-enforcer-webhook with failurePolicy: Fail
   ```
2. The webhook's `failurePolicy: Fail` meant that if the webhook is unreachable, ALL API requests matching the webhook's rules are rejected
3. The pod crashed due to a nil pointer on a new CRD type it didn't recognize (introduced by a team 2 hours earlier)
4. With `failurePolicy: Fail`, the crash created a cluster-wide deployment freeze

## Resolution

1. Deleted the webhook configuration to unblock deployments:
   ```bash
   kubectl delete validatingwebhookconfiguration policy-enforcer-webhook
   ```
2. Immediately verified pending deployments proceeded
3. Fixed the nil pointer bug in policy-enforcer (added CRD type check)
4. Redeployed policy-enforcer with the fix
5. Re-applied webhook configuration with `failurePolicy: Ignore` and `timeoutSeconds: 5`

## Post-Incident Review

- Production admission webhooks MUST use `failurePolicy: Ignore` or have robust HA
- Added PDB and 3 replicas for policy-enforcer
- Added synthetic test that creates a dummy pod every 60s to verify webhook health
- All new CRD introductions must include webhook compatibility testing

## Links

- Related: [[RB-006-failed-deployment-rollback]]
