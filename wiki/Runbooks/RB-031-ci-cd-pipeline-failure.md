---
id: RB-031
title: CI/CD Pipeline Failure Investigation
service: ci-cd
related_services:
  - github-actions
  - argocd
  - all-services
severity: SEV-3
environment: prod
category: deployment
risk_level: low
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - ci-cd
  - pipeline
  - github-actions
  - argocd
  - deployment
  - prod
related_incidents:
  - "[[INC-034-github-actions-runner-token-expiry]]"
  - "[[INC-073-github-actions-self-hosted-runner-compromise]]"
  - "[[INC-029-argocd-sync-loop-crd-mismatch]]"
related_runbooks:
  - "[[RB-006-failed-deployment-rollback]]"
  - "[[RB-025-container-registry-auth-failure]]"
related_guardrails: []
---

## Purpose

Diagnose and recover from CI/CD pipeline failures including runner issues, credential expiry, build failures, and deployment sync problems.

**Desired outcome:** CI/CD pipeline green, deployments flowing normally, no blocked PRs or releases.

## Success Criteria

- Pipeline runs completing successfully
- Runners online and accepting jobs
- ArgoCD/Flux sync status healthy
- No queued deployments blocking releases
- Build artifacts being produced and pushed to registry

## Scope

| Attribute | Value |
|-----------|-------|
| Service | ci-cd pipeline (GitHub Actions, ArgoCD) |
| Related services | github-actions, argocd, all deployed services |
| Environments | prod, staging |
| Use when | Pipelines failing, runners unavailable, sync loops, credential errors |
| Do NOT use when | Application code error causing test failures (fix the code) |
| Risk level | Low (pipeline repair doesn't affect running services) |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] Access to CI/CD platform (GitHub Actions, ArgoCD)
- [ ] Runner host access (if self-hosted)
- [ ] Knowledge of which pipeline is failing

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| GitHub Actions UI | Workflow inspection | Repo admin |
| ArgoCD CLI/UI | Sync status | Admin |
| SSH | Self-hosted runner access | sudo |
| `kubectl` | ArgoCD pod operations | Cluster admin |

## Trigger

- All pipelines queued (no available runners)
- Specific pipeline failing repeatedly with infrastructure error
- ArgoCD showing `OutOfSync` or sync loop
- Deployment blocked (cannot release)

## Triage

1. Identify failure type
   ```bash
   # GitHub Actions: check workflow run status in UI
   # ArgoCD:
   argocd app list | grep -v Healthy
   ```

2. Check runner availability
   ```bash
   # Self-hosted runners:
   ssh runner-01 systemctl status actions.runner.*.service
   ```

3. Check for credential issues
   ```bash
   # Look for 401/403 in pipeline logs
   ```

## Investigation

1. **Runner issues (jobs queued indefinitely)**
   ```bash
   # Check runner disk space:
   ssh runner-01 df -h
   # Check runner service status:
   ssh runner-01 journalctl -u actions.runner.* --since "10 min ago"
   ```

2. **ArgoCD sync loop**
   ```bash
   argocd app get <app-name> --show-operation
   kubectl logs -l app.kubernetes.io/name=argocd-application-controller -n argocd --tail=50
   ```

3. **Build failures (dependency/registry issues)**
   ```bash
   # Check pipeline logs for: npm install failure, Docker build failure, push failure
   ```

4. **Decision point:**
   - IF runners down → proceed to Mitigation Option A
   - IF credential expired → proceed to Mitigation Option B
   - IF ArgoCD sync loop → proceed to Mitigation Option C
   - IF build dependency issue → proceed to Mitigation Option D

## Mitigation

### Option A: Fix runners

```bash
# Clean up disk and restart:
ssh runner-01 "docker system prune -af && sudo systemctl restart actions.runner.*.service"
```

### Option B: Refresh credentials

```bash
# GitHub Actions token:
# Re-register runner with new token from Settings → Actions → Runners
# ECR: See [[RB-025-container-registry-auth-failure]]
```

### Option C: Fix ArgoCD sync loop

```bash
# Force sync with prune:
argocd app sync <app-name> --prune --force
# If CRD mismatch, refresh resource state:
argocd app get <app-name> --hard-refresh
```

### Option D: Fix build dependency

```bash
# Clear build cache:
# GitHub Actions: add workflow step to clear cache
# Docker: Use --no-cache flag temporarily
```

**After mitigation:** Re-run failed pipeline, verify success.

## Verification

- [ ] Pipeline run succeeds end-to-end
- [ ] Runners showing online status
- [ ] ArgoCD apps in Synced/Healthy state
- [ ] Deployment artifacts appearing in registry

## Failure Signals

- Multiple different pipeline steps failing
- Runner keeps going offline after restart
- ArgoCD sync loop continues after force sync

## Rollback

1. **If ArgoCD force sync broke something:** `argocd app rollback <app-name>`
2. **If runner re-registration broke workflow:** Restore runner config from backup

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| All runners down >30 min | Platform team | #platform-support | 15 min |
| Cannot deploy to prod (release blocked) | EM + Release manager | #releases | 10 min |
| ArgoCD cluster-wide sync failure | Platform team | PagerDuty | 10 min |

## Notes

- **Self-hosted runners accumulate garbage.** See [[INC-073-github-actions-self-hosted-runner-compromise]] — always set up cleanup crons.
- **ArgoCD sync loops** often caused by CRD version drift or resources with server-managed fields. See [[INC-029-argocd-sync-loop-crd-mismatch]].
- **GitHub runner tokens expire.** Re-register runners before expiry. See [[INC-034-github-actions-runner-token-expiry]].

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Stop a runner in staging, verify job re-routing and recovery.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Platform Team | Initial publication |
