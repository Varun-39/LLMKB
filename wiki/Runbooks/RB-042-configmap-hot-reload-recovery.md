---
id: RB-042
title: ConfigMap Hot-Reload Crash Recovery and Safe Rollback
service: payment-service
related_services:
  - auth-service
  - reporting-service
severity: SEV-1
environment: prod
category: deployment
risk_level: high
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - kubernetes
  - configmap
  - hot-reload
  - crash
  - rollback
  - payment-service
  - prod
---

## Purpose

Recover from a ConfigMap update that caused application pods to crash (panic, parse error, or invalid config) via hot-reload, and restore service using the last known-good configuration.

**Desired outcome:** All pods Running with valid configuration, service traffic flowing normally.

## Success Criteria

- All pods Running and Ready (no CrashLoopBackOff)
- Service error rate back to baseline
- Active ConfigMap contains valid, parseable configuration
- Hot-reload validated before applying to all pods

## Scope

| Attribute | Value |
|-----------|-------|
| Service | payment-service (primary), any service using ConfigMap hot-reload |
| Environments | prod |
| Use when | ConfigMap update causes pods to crash simultaneously (CrashLoopBackOff, Error) |
| Do NOT use when | Pod crash unrelated to ConfigMap (use RB-007 instead) |
| Risk level | High — reverting config may lose intentional changes |
| Estimated duration | 10–15 minutes |
| Approval required | No (emergency recovery) |

## Prerequisites

- [ ] `kubectl` access to the affected namespace
- [ ] Access to Git repo containing ConfigMap manifests (for the stable version)
- [ ] Know the last known-good ConfigMap version (check git history or prior deployment)

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Inspect and patch ConfigMap, restart pods | Namespace admin |
| `git` | Find last known-good ConfigMap | Read access |

## Trigger

- Alert: `payment-service all pods down` or high CrashLoopBackOff count
- Symptom: All pods crashed within 30 seconds of each other (simultaneous = config event)
- Log pattern: `panic: yaml: unexpected EOF`, `invalid configuration`, `failed to parse config`

## Triage

1. Check if all pods crashed simultaneously (hot-reload pattern):
   ```bash
   kubectl get pods -n <namespace> -o wide
   # All pods show Error or CrashLoopBackOff with similar AGE
   ```
2. Check crash reason in logs:
   ```bash
   kubectl logs -n <namespace> <pod-name> --previous | tail -20
   # Look for: config parse error, YAML error, missing required field
   ```
3. Check if a ConfigMap was updated recently:
   ```bash
   kubectl get configmap -n <namespace> -o yaml | grep -A3 "last-applied-configuration" | grep resourceVersion
   # Compare timestamp to when pods crashed
   ```

## Investigation

1. **Identify the bad ConfigMap**
   ```bash
   kubectl get configmap <config-name> -n <namespace> -o yaml
   # Try to parse it manually: echo '<value>' | python3 -c "import yaml,sys;yaml.safe_load(sys.stdin)"
   ```
2. **Find last known-good config in git**
   ```bash
   git log --oneline -- config/<configmap-file>.yaml | head -5
   git show <last-good-commit>:config/<configmap-file>.yaml
   ```
3. **Decision point:**
   - IF config is clearly malformed (YAML parse error) → Option A (revert ConfigMap)
   - IF config is syntactically valid but semantically wrong → Option A (revert) + document
   - IF unsure what changed → Option A (revert), investigate after recovery

## Mitigation

### Option A: Revert ConfigMap to last known-good version

```bash
# Apply the last-good version from git:
git show <stable-commit>:config/<configmap-file>.yaml | kubectl apply -f - -n <namespace>

# OR manually patch if small change:
kubectl edit configmap <config-name> -n <namespace>
# Fix the malformed field
```

### Option B: Restart pods to pick up reverted ConfigMap

```bash
# Pods using mounted ConfigMaps need a restart to re-read the file:
kubectl rollout restart deployment/<app> -n <namespace>
kubectl rollout status deployment/<app> -n <namespace>
```

**After mitigation:** Watch first pod start; confirm no config parse errors in logs before others start.

## Verification

- [ ] `kubectl get pods -n <namespace>` shows all pods Running
- [ ] No config parse errors in pod logs
- [ ] Service responding to health endpoint

```bash
kubectl exec -n <namespace> deploy/<app> -- curl -s localhost:8080/health
# Expected: HTTP 200
```

## Failure Signals

- Pods crash again after ConfigMap revert (check if inotify hot-reload is re-reading a different path)
- ConfigMap revert did not propagate to mounted volume (Kubernetes volume propagation has up to 60s delay — wait before restarting)
- All pods down and unable to restart (readiness probe blocking — check if config path is correct)

## Rollback

- After service is stable, create a proper fix for the ConfigMap in version control.
- Submit PR with review before re-applying the intended change.
- Test ConfigMap changes in staging with hot-reload enabled before prod deployment.

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Cannot locate last-good ConfigMap in git | On-call senior + owning team | #incident-response | 5 min |
| All replicas down and rollback not fixing (SEV-1) | EM + IC | #incident-response | Immediate |
| Config change touched secrets or auth config | Security review before revert | #security-urgent | Before acting |

## Notes

- ConfigMap volume propagation has a Kubernetes-level delay (typically 30–60s). Wait before restarting pods or you may see the bad config again briefly.
- Long-term fix: validate YAML config files in CI before allowing ConfigMap updates to prod.
- Long-term fix: stagger hot-reload (reload one pod at a time) rather than all simultaneously.
- See [[INC-086-k8s-configmap-hot-reload-crash]] for the incident that motivated this runbook.

## Maintenance

- **Last tested:** 2026-05-20
- **Review cycle:** Quarterly
- **Next review:** 2026-08-20
- **Test method:** Apply a malformed ConfigMap in staging with hot-reload; execute recovery procedure.

## last Updated

| Date | Author | Change |
|------|--------|--------|
| 2026-05-20 | SRE Team | Initial publication |
