---
id: RB-040
title: Kubernetes Pod Scheduling Failure — Affinity and Topology Diagnosis
service: general
related_services:
  - payment-service
  - auth-service
  - reporting-service
severity: SEV-2
environment: prod
category: deployment
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - kubernetes
  - scheduling
  - affinity
  - pod-pending
  - topology
  - prod
---

## Purpose

Diagnose and resolve Kubernetes pod scheduling failures where pods remain in `Pending` state due to affinity, anti-affinity, or topology spread constraint misconfigurations.

**Desired outcome:** All pods scheduled and Running, deployment rollout completed.

## Success Criteria

- All desired pods in `Running` state
- No `Pending` pods older than 2 minutes
- Scheduler events show successful binding
- No `0/N nodes available` errors

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any Kubernetes workload |
| Environments | prod, staging |
| Use when | Pods stuck in Pending with affinity/topology errors in events |
| Do NOT use when | Pods Pending due to resource quota (use RB-037) or node NotReady (use RB-019) |
| Risk level | Medium — changing affinity rules may affect workload placement security |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to the affected namespace and node objects
- [ ] Understand the intent of the affinity rule (check with owning team if unclear)

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Inspect pods, nodes, and events | Namespace admin |

## Trigger

- Symptom: New pods stuck in `Pending` state after deploy or scale-up
- Event: `0/N nodes available: N node(s) didn't match pod affinity rules`
- Deployment rollout hangs without completing

## Triage

1. Check if pods are Pending:
   ```bash
   kubectl get pods -n <namespace> | grep Pending
   ```
2. Check the scheduling failure reason:
   ```bash
   kubectl describe pod <pending-pod> -n <namespace> | grep -A5 "Events:"
   # Look for: "didn't match pod affinity", "didn't match node affinity", "didn't satisfy topology"
   ```
3. Confirm this is affinity (not quota, not resources):
   ```bash
   # Quota issue: "exceeded quota" in events
   # Resource issue: "Insufficient cpu/memory" in events
   # Affinity issue: "didn't match pod/node affinity rules" in events
   ```

## Investigation

1. **Extract the affinity rule from the deployment**
   ```bash
   kubectl get deploy <name> -n <namespace> -o yaml | grep -A30 affinity
   ```
2. **Check if the required label exists on any node**
   ```bash
   # For nodeAffinity: check node labels
   kubectl get nodes --show-labels | grep <required-label>
   # For podAffinity: check if required pods exist
   kubectl get pods -n <namespace> --show-labels | grep <required-label>
   ```
3. **Check topology spread constraints if present**
   ```bash
   kubectl get deploy <name> -n <namespace> -o yaml | grep -A20 topologySpreadConstraints
   # If whenUnsatisfiable: DoNotSchedule — this is a hard constraint
   ```
4. **Decision point:**
   - IF `required` nodeAffinity with non-existent label → Option A (change to preferred or add label)
   - IF `required` podAffinity with no matching pods → Option A
   - IF topologySpreadConstraint too strict → Option B (relax constraint)
   - IF AZ imbalance causing anti-affinity to block → Option C (reschedule for even spread)

## Mitigation

### Option A: Change required affinity to preferred

```bash
kubectl edit deployment <name> -n <namespace>
# Change: requiredDuringSchedulingIgnoredDuringExecution
# To:     preferredDuringSchedulingIgnoredDuringExecution (with weight: 1-100)
```

### Option B: Relax topology spread constraint

```bash
kubectl edit deployment <name> -n <namespace>
# Change: whenUnsatisfiable: DoNotSchedule
# To:     whenUnsatisfiable: ScheduleAnyway
```

### Option C: Delete and reschedule pending pods for even spread

```bash
# First ensure anti-affinity is not hard (required)
kubectl delete pod <pending-pod-name> -n <namespace>
# Scheduler will retry with updated cluster state
```

**After mitigation:** Monitor rollout until all pods reach Running.

## Verification

- [ ] `kubectl get pods -n <namespace>` shows all pods Running
- [ ] `kubectl rollout status deployment/<name> -n <namespace>` shows success
- [ ] No new Pending pods after 5 minutes

```bash
kubectl get pods -n <namespace> -o wide
# Expected: all pods Running, distributed across expected nodes/zones
```

## Failure Signals

- Pods still Pending after affinity change (check for additional constraints)
- New pods pending after fix (node label was added but not to all required nodes)
- Other deployments being evicted after scheduling freed (different resource issue)

## Rollback

- Revert affinity change if workload spread requirement was intentional and security-relevant:
  ```bash
  kubectl edit deployment <name> -n <namespace>
  # Restore original affinity rule
  ```
- Notify owning team of the change made.

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Cannot determine if affinity rule is intentional (security-related) | Security + owning team | #change-management | Before changing |
| All nodes are tainted and no tolerations exist | Platform team | #platform-support | 10 min |
| Multi-zone scheduling issue during AZ outage | Platform Lead | #incident-response | 5 min |

## Notes

- `requiredDuringScheduling` with a non-existent label = pods NEVER schedule. Always test affinity rules in staging first.
- AZ-spread anti-affinity (`topologyKey: topology.kubernetes.io/zone`) is strongly recommended for stateless prod workloads.
- See [[INC-080-k8s-pod-affinity-misconfiguration-scheduling-failure]] and [[INC-094-node-affinity-zone-imbalance-az-failure]].

## Maintenance

- **Last tested:** 2026-05-18
- **Review cycle:** Quarterly
- **Next review:** 2026-08-18
- **Test method:** Deploy a pod with a non-existent node label requirement in staging; verify triage finds it.

## last Updated

| Date | Author | Change |
|------|--------|--------|
| 2026-05-18 | Platform Team | Initial publication |
