---
id: INC-100
title: Kubernetes Resource Quota Exhaustion Blocked Emergency Deployment
severity: SEV-2
service: payment-service
environment: prod
category: deployment-failure
date: 2026-05-11
duration: "38m"
tags:
  - incident
  - kubernetes
  - resource-quota
  - namespace
  - deployment
  - payment-service
  - prod
---

## Summary

During an emergency hotfix deployment for payment-service, `kubectl apply` was silently rejected by a namespace ResourceQuota that had been set during a cost-control sprint. The quota allowed 10 CPU cores per namespace; running deployments already consumed 9.8 cores. The new pods requested 0.5 CPU each, exceeding the quota. The deployment appeared to succeed (kubectl exited 0) but pods never started, delaying a critical fix for 38 minutes while engineers debugged why pods weren't appearing.

## Symptoms

- `kubectl apply` exited 0 — no error
- `kubectl get pods -n payments`: no new pods appearing
- `kubectl get replicaset -n payments`: new RS shows `0/3 desired` with `FailedCreate` events
- ReplicaSet events: `exceeded quota: payments-quota, requested: cpu=0.5, used: cpu=9.8, limited: cpu=10`

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | Delayed hotfix for payment bug affecting ~1,100 users |
| Services degraded | payment-service (bug persisted 38 extra minutes) |
| Revenue impact | ~$7.2K (additional impact from delayed fix) |
| Duration | 16:00 → 16:38 UTC (38 min) |
| Data loss | None |
| SLA breach | Yes — hotfix deployment time SLA breached |
| Customer comms | Status page already updated from prior incident |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 16:00 | Emergency hotfix deployment triggered |
| 16:01 | `kubectl apply` exits 0 — engineers assume success |
| 16:10 | No new pods visible; investigation starts |
| 16:15 | ReplicaSet events reveal quota breach |
| 16:20 | Quota temporarily raised to 15 CPU |
| 16:38 | Hotfix pods running; payment bug resolved |

## Diagnosis

1. Checked why new pods didn't start:
   ```bash
   kubectl get replicaset -n payments
   # payment-service-hotfix: DESIRED=3, CURRENT=0, READY=0
   ```
2. Checked replicaset events:
   ```bash
   kubectl describe replicaset payment-service-hotfix -n payments | grep -A5 Events
   # Warning  FailedCreate: exceeded quota: payments-quota, requested: cpu=0.5, used: cpu=9.8, limited: cpu=10
   ```
3. Confirmed quota settings:
   ```bash
   kubectl describe resourcequota payments-quota -n payments
   # cpu: 9.8/10
   # memory: 18Gi/24Gi
   ```

## Resolution

1. **Mitigate:** Temporarily raised CPU quota for emergency:
   ```bash
   kubectl patch resourcequota payments-quota -n payments \
     --type=json -p='[{"op":"replace","path":"/spec/hard/cpu","value":"15"}]'
   ```
2. Deployment immediately succeeded; pods started within 60 seconds
3. **After hotfix stabilised:** scaled down non-critical pods to reclaim headroom, reverted quota to 12 CPU (previously 10)

## Post-Incident Review

**What went well:**
- ReplicaSet events contained exact quota breach information — diagnosis clear once found

**What needs improvement:**
- `kubectl apply` success (exit 0) is misleading when pods fail due to quota — no operator feedback
- Quota headroom not monitored; no alert before reaching 95% of quota
- Emergency deployment runbook did not include quota check step

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add quota headroom alert: namespace CPU/memory > 85% of limit | Observability | 2026-05-18 | Open |
| Add quota check to emergency deployment runbook | SRE | 2026-05-18 | Open |
| Add 20% quota headroom buffer to all production namespaces | Platform | 2026-05-18 | Open |
| Deploy `kube-capacity` CLI to make quota visibility easier during incidents | Platform | 2026-05-25 | Open |

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]], [[RB-019-kubernetes-node-notready]]
- Related incidents: [[INC-013-k8s-pending-pods-resource-pressure]], [[INC-028-k8s-admission-webhook-timeout]]
