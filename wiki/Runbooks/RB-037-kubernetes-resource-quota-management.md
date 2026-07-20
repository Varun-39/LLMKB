---
id: RB-037
title: Kubernetes Resource Quota Management and Emergency Headroom Recovery
service: general
related_services:
  - payment-service
  - auth-service
  - reporting-service
severity: SEV-2
environment: prod
category: resource-exhaustion
risk_level: medium
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - kubernetes
  - resource-quota
  - namespace
  - deployment
  - prod
---

## Purpose

Diagnose and resolve Kubernetes ResourceQuota exhaustion blocking pod scheduling or deployments, and restore headroom for emergency deployments.

**Desired outcome:** Deployment succeeds, pods reach Running state, namespace quota utilisation below 80%.

## Success Criteria

- Target deployment pods are Running and Ready
- Namespace quota utilisation < 80% CPU and memory
- No `FailedCreate` events on ReplicaSets
- No active quota-related alerts

## Scope

| Attribute | Value |
|-----------|-------|
| Service | All services in quota-managed namespaces |
| Environments | prod, staging |
| Use when | Deployment appears to succeed but no pods start; `FailedCreate` events mentioning quota |
| Do NOT use when | Pod fails due to node resource pressure (use RB-019 instead) |
| Risk level | Medium — quota increase may allow over-provisioning |
| Estimated duration | 10–15 minutes |
| Approval required | No (emergency increase); yes for permanent quota change |

## Prerequisites

- [ ] `kubectl` access with `get/patch resourcequota` permission
- [ ] Know the current CPU/memory requests for the deployment being applied
- [ ] Confirm no unrelated large deployments running that can be scaled down

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Inspect and patch ResourceQuota | Namespace admin |
| `kube-capacity` (optional) | Visual quota summary | Read access |

## Trigger

- Alert: `NamespaceQuotaUsage > 85%`
- Symptom: `kubectl apply` exits 0 but no new pods appear
- Event: `FailedCreate: exceeded quota` on ReplicaSet

## Triage

1. Check if deployment has ReplicaSet with 0 pods:
   ```bash
   kubectl get replicaset -n <namespace>
   # If DESIRED > 0 and CURRENT = 0, quota is likely the cause
   ```
2. Check ReplicaSet events for quota message:
   ```bash
   kubectl describe replicaset <rs-name> -n <namespace> | grep -A3 "FailedCreate"
   # Warning FailedCreate: exceeded quota: ..., requested: cpu=X, used: cpu=Y, limited: cpu=Z
   ```
3. If quota message absent → check node resource pressure (different problem).

## Investigation

1. **Check current quota utilisation**
   ```bash
   kubectl describe resourcequota -n <namespace>
   # Shows used vs hard limit for CPU, memory, pods
   ```
2. **Identify which deployments are consuming the most quota**
   ```bash
   kubectl top pods -n <namespace> --sort-by=cpu | head -10
   ```
3. **Calculate headroom needed for target deployment**
   ```bash
   kubectl get deploy <target> -n <namespace> -o jsonpath='{.spec.template.spec.containers[0].resources.requests}'
   # Multiply by desired replicas to get total request
   ```
4. **Decision point:**
   - IF non-critical deployments can be scaled down → Option A
   - IF emergency deployment blocks urgent fix → Option B (temporary quota increase)
   - IF quota needs permanent increase → Option C (change management)

## Mitigation

### Option A: Scale down non-critical workloads to free headroom

```bash
# Identify low-priority deployments (e.g. batch jobs, staging-like workloads)
kubectl get deployments -n <namespace> -o custom-columns=NAME:.metadata.name,REPLICAS:.spec.replicas
# Scale down non-critical one:
kubectl scale deployment/<non-critical> -n <namespace> --replicas=0
```

### Option B: Temporary quota increase for emergency deployment

```bash
# Increase CPU limit temporarily (document in incident channel)
kubectl patch resourcequota <quota-name> -n <namespace> \
  --type=json -p='[{"op":"replace","path":"/spec/hard/cpu","value":"15"}]'
# Re-apply the blocked deployment:
kubectl rollout restart deployment/<target> -n <namespace>
```

### Option C: Permanent quota adjustment (change management)

```bash
# Edit quota manifest and apply via GitOps
kubectl edit resourcequota <quota-name> -n <namespace>
# Increase cpu and/or memory limits
# Submit PR for infra repo change
```

**After mitigation:** Monitor for 10 minutes to confirm pods reach Ready state.

## Verification

- [ ] `kubectl get pods -n <namespace>` shows new pods Running
- [ ] `kubectl describe resourcequota -n <namespace>` shows utilisation < 80%
- [ ] No new `FailedCreate` events

```bash
kubectl describe resourcequota -n <namespace>
# Expected: used: cpu=X (<80% of hard limit)
```

## Failure Signals

- Pods still not creating after quota increase (check node pressure instead)
- Quota increase applied but wrong namespace targeted
- Other deployments evicted due to node resource pressure after quota freed

## Rollback

1. **Revert temporary quota increase** once emergency is resolved:
   ```bash
   kubectl patch resourcequota <quota-name> -n <namespace> \
     --type=json -p='[{"op":"replace","path":"/spec/hard/cpu","value":"10"}]'
   ```
2. **Restore scaled-down deployments:**
   ```bash
   kubectl scale deployment/<non-critical> -n <namespace> --replicas=<original>
   ```
3. Notify #change-management of temporary change and revert.

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| No pods after quota increase | Platform/SRE | #platform-support | 10 min |
| Node resource pressure (not quota) | Infrastructure team | #platform-support | 10 min |
| Quota increase risks cluster stability | Platform Lead | #change-management | Before proceeding |

## Notes

- Always record temporary quota increases in the incident channel — they must be reverted.
- `kubectl apply` exit 0 does NOT mean pods started. Always verify with `kubectl get pods`.
- See [[INC-100-k8s-resource-quota-blocked-deployment]] for an example of this causing emergency delay.
- See also [[INC-013-k8s-pending-pods-resource-pressure]] for node-level resource pressure (different issue).

## Maintenance

- **Last tested:** 2026-05-18
- **Review cycle:** Quarterly
- **Next review:** 2026-08-18
- **Test method:** Apply a deployment that exceeds quota in staging; verify error is caught by triage step.

## last Updated

| Date | Author | Change |
|------|--------|--------|
| 2026-05-18 | Platform Team | Initial publication |
