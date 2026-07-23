---
id: INC-093
title: Mutable Image Tag Caused Silent Code Regression After Rollback
severity: SEV-2
service: frontend
environment: prod
category: deployment-failure
date: 2026-04-27
duration: "4h 20m"
tags:
  - incident
  - container
  - image-tag
  - mutable
  - rollback
  - frontend
  - prod
error_family: unknown
resolution_runbook: RB-006
resolution_outcome: resolved
---

## Summary

A frontend deployment used the `latest` image tag. When a critical bug was detected and `kubectl rollout undo` was issued, Kubernetes redeployed pods using the same `latest` tag — which by then pointed to the same (broken) image because the registry had been overwritten. The rollback appeared successful (pods Running, Ready) but the bug persisted, costing 4+ hours of debugging before the root cause was identified.

## Symptoms

- Post-rollback: pods Running/Ready but bug still present
- `kubectl rollout history` shows correct revision timestamps but identical image digest
- Users still reporting checkout button malfunction
- Grafana: frontend error rate unchanged after rollback

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~6,000 users affected by checkout UI bug |
| Services degraded | frontend (checkout flow broken) |
| Revenue impact | ~$22K (4.5h of degraded checkout conversion) |
| Duration | 10:00 → 14:20 UTC (4h 20m — including 3h false-recovery period) |
| Data loss | None |
| SLA breach | No |
| Customer comms | Status page updated at 10:15 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 10:00 | frontend v2.8.1 deployed using `latest` tag |
| 10:05 | Checkout bug detected |
| 10:08 | `kubectl rollout undo` issued |
| 10:10 | Pods show Running/Ready — assumed recovered |
| 13:20 | Engineer notices bug still present |
| 13:35 | Image digest comparison reveals identical images |
| 14:00 | Explicit digest of last good image located in registry |
| 14:20 | Redeployed with explicit SHA digest; bug resolved |

## Diagnosis

1. Confirmed rollback "succeeded" but image is the same:
   ```bash
   kubectl get pods -n frontend -o jsonpath='{.items[*].spec.containers[0].image}'
   # frontend:latest (×3 pods)
   kubectl get pods -n frontend -o jsonpath='{.items[0].status.containerStatuses[0].imageID}'
   # sha256:abc123def  — same as broken image
   ```
2. Checked rollout history:
   ```bash
   kubectl rollout history deployment/frontend -n frontend
   # REVISION 1: frontend:latest
   # REVISION 2: frontend:latest  — both point to same tag
   ```
3. Located last good digest in CI build logs:
   ```bash
   # CI build for v2.8.0: sha256:fff999aaa  (good)
   # CI build for v2.8.1: sha256:abc123def  (bad, now tagged :latest)
   ```

## Resolution

1. Redeployed using explicit SHA digest of last good build:
   ```bash
   kubectl set image deployment/frontend -n frontend \
     frontend=registry.company.com/frontend@sha256:fff999aaa
   ```
2. Bug immediately resolved after pod restart

## Post-Incident Review

**What went well:**
- Registry build history preserved SHA digests — recovery was possible

**What needs improvement:**
- Mutable `latest` tag used in production
- Rollback gives false confidence — pods "running" does not mean "correct image"

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Enforce immutable image tags in all production deployments (no `latest`) | Platform | 2026-05-04 | Open |
| Add kyverno policy to reject deployments with `:latest` or no digest | Platform | 2026-05-04 | Open |
| Add image digest to deployment verification step in runbook | SRE | 2026-05-04 | Open |

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]]
- Related incidents: [[INC-011-rollback-failed-frontend]], [[INC-012-k8s-imagepullbackoff-reports]]
