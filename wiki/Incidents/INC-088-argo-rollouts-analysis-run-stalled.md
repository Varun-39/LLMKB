---
id: INC-088
title: Argo Rollouts AnalysisRun Stalled Blocking Canary Promotion
severity: SEV-3
service: payment-service
environment: prod
category: deployment-failure
date: 2026-04-17
duration: "3h 05m"
tags:
  - incident
  - argo-rollouts
  - canary
  - analysis-run
  - deployment
  - payment-service
  - prod
error_family: unknown
resolution_runbook: RB-006
resolution_outcome: resolved
---

## Summary

A canary deployment of payment-service v2.4.1 stalled because the Argo Rollouts AnalysisRun could not reach the Prometheus endpoint to evaluate success metrics. A network policy change earlier that day blocked the Argo Rollouts controller's egress to Prometheus. The canary sat frozen at 20% traffic for 3 hours before the root cause was identified.

## Symptoms

- Argo Rollouts dashboard: canary stuck at 20% for >30 minutes
- AnalysisRun status: `Running` but no measurements being recorded
- Argo Rollouts controller logs: `dial tcp prometheus:9090: i/o timeout`
- payment-service v2.4.1: running at 20% traffic, no errors, but promotion blocked

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | No user impact — canary was healthy; only deployment blocked |
| Services degraded | Deployment pipeline (payment-service stuck, blocking next release) |
| Revenue impact | N/A |
| Duration | 11:00 → 14:05 UTC (3h 05m) |
| Data loss | None |
| SLA breach | No |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 09:30 | Network policy change applied (blocked Argo Rollouts egress) |
| 11:00 | payment-service canary rollout started |
| 11:30 | AnalysisRun stalls (no measurements) |
| 12:00 | Engineer notices canary not progressing |
| 13:30 | Network policy identified as root cause |
| 14:05 | Network policy updated; AnalysisRun completed; promotion succeeded |

## Diagnosis

1. Checked AnalysisRun status:
   ```bash
   kubectl get analysisrun -n payments
   # payment-canary-xxxx: Running (3h)  — should complete in 15 min
   kubectl describe analysisrun payment-canary-xxxx -n payments
   # Message: dial tcp 10.0.2.10:9090: i/o timeout
   ```
2. Confirmed Prometheus reachable from other pods but not from Argo controller:
   ```bash
   kubectl exec -n argo-rollouts deploy/argo-rollouts -- curl -s http://prometheus:9090/-/healthy
   # (no response — timeout)
   ```
3. Traced to network policy applied at 09:30:
   ```bash
   kubectl get networkpolicy -n argo-rollouts
   # argo-rollouts-default-deny: deny all egress except port 443
   ```

## Resolution

1. **Fixed network policy** to allow Argo Rollouts egress to Prometheus:
   ```bash
   kubectl apply -f - <<EOF
   apiVersion: networking.k8s.io/v1
   kind: NetworkPolicy
   metadata:
     name: allow-argo-prometheus
     namespace: argo-rollouts
   spec:
     podSelector: {}
     egress:
     - to:
       - namespaceSelector:
           matchLabels:
             name: monitoring
       ports:
       - port: 9090
   EOF
   ```
2. AnalysisRun immediately resumed measurements and completed within 10 minutes
3. Canary promoted to 100%

## Post-Incident Review

**What went well:**
- Canary was healthy throughout; no user impact

**What needs improvement:**
- Network policy change had no impact analysis for Argo Rollouts
- No alert when AnalysisRun produces no measurements for >15 minutes

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Document Argo Rollouts network requirements in NetworkPolicy playbook | Platform | 2026-04-24 | Open |
| Add alert: AnalysisRun running > 30 min with 0 measurements | Observability | 2026-04-24 | Open |

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]]
- Related incidents: [[INC-010-release-failed-canary-api]], [[INC-029-argocd-sync-loop-crd-mismatch]]
