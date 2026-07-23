---
id: INC-060
title: Pod Security Admission Blocked Critical Deployment
severity: SEV-2
service: payment-service
environment: prod
category: deployment-failure
date: 2026-05-28
duration: "42m"
tags:
  - incident
  - kubernetes
  - pod-security
  - admission
  - deployment
  - high
  - prod
error_family: oom
resolution_runbook: RB-006
resolution_outcome: resolved
---

## Summary

After enabling Pod Security Admission (PSA) in `enforce` mode on the `payments` namespace, the next payment-service deployment was rejected because the pod spec included `securityContext.privileged: true` (used for the debug sidecar in the Helm chart). No new pods could be created, and the existing pods (running before PSA was enabled) continued serving traffic until they crashed from a memory leak 42 minutes later, at which point no replacement pods could be scheduled.

## Symptoms

- Deployment stuck at 0 available replicas
- Events: `pods "payment-service-xyz" is forbidden: violates PodSecurity "restricted:latest"`
- Existing pods running but aging (no new replicas)
- After 42 min: existing pods OOMKilled, complete outage

## Diagnosis

1. Checked deployment events
   ```bash
   kubectl get events -n payments --sort-by='.lastTimestamp' | grep forbidden
   # violates PodSecurity "restricted:latest": privileged (container "debug-sidecar")
   ```

2. PSA label applied to namespace 2 hours before incident
   ```bash
   kubectl get namespace payments -o jsonpath='{.metadata.labels}' | jq .
   # "pod-security.kubernetes.io/enforce": "restricted"
   ```

3. Helm chart included debug sidecar with `privileged: true` (dev dependency leaked to prod)

## Resolution

1. **Mitigate:** Temporarily set PSA to `warn` mode to allow deployment
   ```bash
   kubectl label namespace payments pod-security.kubernetes.io/enforce=baseline --overwrite
   ```

2. **Fix:** Removed debug sidecar from prod Helm values, redeployed

3. **Verify:** Deployment succeeded with restricted policy

## Post-Incident Review

- PSA enforcement should be applied with a dry-run audit first
- Added CI step: `kubectl auth can-i create pods --dry-run=server` against namespace policy
- Debug sidecars gated behind Helm value `debug.enabled` (false in prod)
- PSA changes now require 24-hour audit period before enforcement

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]]
- Related incidents: [[INC-028-k8s-admission-webhook-timeout]]
