---
id: RB-006
title: Failed Deployment Rollback (Kubernetes)
service: "*"
related_services:
  - api-gateway
  - payment-service
  - auth-service
  - frontend
severity: SEV-2
environment: prod
category: deployment
risk_level: high
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - deployment
  - rollback
  - kubernetes
  - canary
  - config
  - prod
related_incidents:
  - "[[INC-010-release-failed-canary-api]]"
  - "[[INC-011-rollback-failed-frontend]]"
  - "[[INC-019-broken-feature-flag-auth]]"
  - "[[INC-020-bad-config-rollout-payment]]"
  - "[[INC-012-k8s-imagepullbackoff-reports]]"
related_runbooks:
  - "[[RB-007-pod-crash-investigation]]"
related_guardrails: []
---

## Purpose

Diagnose and recover from a failed Kubernetes deployment, covering standard rollbacks, canary aborts, database migration conflicts, config errors, feature flag issues, and image pull failures.

**Desired outcome:** Service running on last known good version with error rate at pre-deployment baseline.

## Success Criteria

Before closing the incident or declaring the runbook complete, ALL of the following must be true:

- All pods in `Running` state with 0 restarts in last 5 minutes
- Application error rate at pre-deployment baseline
- Health endpoint returning 200
- No new alerts in 15 minutes
- Confirmed image tag matches expected last-known-good version

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any Kubernetes service with a failed deployment |
| Related services | api-gateway, payment-service, auth-service, frontend |
| Environments | prod, staging |
| Use when | `*-DeploymentFailed`, `*-CanaryErrorRate`, error spike post-deploy, or pods in ImagePullBackOff/CrashLoopBackOff after release |
| Do NOT use when | Service was already degraded before deployment (pre-existing issue) |
| Risk level | High (database migrations may be irreversible) |
| Estimated duration | 10–15 minutes |
| Approval required | No (but DBA approval required if DB migration involved) |

## Prerequisites

- [ ] `kubectl` access to affected cluster and namespace
- [ ] Knowledge of which deployment triggered the issue
- [ ] Access to deployment pipeline (Argo Rollouts, Flux, or CI/CD tool)
- [ ] Git access to service repository (for config/manifest review)
- [ ] Confirm whether the deployment included a database migration

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Pod/deployment operations | Cluster admin |
| Git | Config/manifest review | Read access |
| Deployment pipeline UI | Argo/Flux/Jenkins status | Read/Write access |
| Grafana | Error rate and latency verification | Read access |
| AWS ECR | Image tag verification | Read access |

## Trigger

- Alert: `*-DeploymentFailed`, `*-CanaryErrorRate`, `*-RolloutStalled`
- Symptom: Deployment pipeline canary analysis failed, rollout paused or stuck
- Symptom: Application error rate spike immediately after a deployment (5%+ error rate)
- Symptom: Pods in `ImagePullBackOff`, `CrashLoopBackOff`, or `Error` state post-deploy
- Symptom: New error type or broken feature appearing after release window

## Triage

1. Confirm the deployment state
   ```bash
   kubectl rollout status deployment/<deployment> -n <namespace>
   # What to look for: "not progressing" = rollout stuck
   kubectl get pods -n <namespace> -l app=<service-name>
   # What to look for: CrashLoopBackOff, ImagePullBackOff, Error
   ```

2. Assess blast radius — single service or multi-service release
   ```bash
   kubectl rollout history deployment/<deployment> -n <namespace>
   # Note current and previous revision numbers
   ```

3. **CRITICAL:** Check if a database migration was part of this deployment
   ```bash
   kubectl logs <pod-name> -n <namespace> --previous | grep -i "migration\|flyway\|liquibase\|alembic"
   # IF migration ran → rollback is complex (see Mitigation Option C)
   ```

4. Wrong symptoms? → Try [[RB-007-pod-crash-investigation]]

## Investigation

1. **Check what changed in the latest rollout**
   ```bash
   kubectl rollout history deployment/<deployment> -n <namespace> --revision=<current>
   # What to look for: image tag, env vars, resource changes
   ```

2. **Check pod logs for crash reason**
   ```bash
   kubectl logs <new-pod-name> -n <namespace> --tail=100
   kubectl logs <pod-name> -n <namespace> --previous --tail=100
   ```

3. **Check if it's an image pull issue**
   ```bash
   kubectl describe pod <pod-name> -n <namespace> | grep -A10 "Events"
   # What to look for: "Failed to pull image", "unauthorized", "not found"
   ```

4. **Check if a ConfigMap/Secret changed**
   ```bash
   kubectl get configmap <service>-config -n <namespace> -o yaml
   git diff HEAD~1 -- k8s/prod/<service>-config.yaml
   # What to look for: typos, zero values, schema mismatches
   ```

5. **Check canary metrics** (if using progressive delivery)
   ```bash
   kubectl argo rollouts get rollout <rollout-name> -n <namespace>
   kubectl argo rollouts status <rollout-name> -n <namespace>
   ```

6. **Decision point:**
   - IF standard deployment failure (no DB migration) → proceed to Mitigation Option A
   - IF canary failure → proceed to Mitigation Option B
   - IF DB migration involved → proceed to Mitigation Option C
   - IF bad config (ConfigMap/Secret) → proceed to Mitigation Option D
   - IF feature flag issue → proceed to Mitigation Option E
   - IF ImagePullBackOff → proceed to Mitigation Option F
   - IF unclear → escalate (see Escalation section)

## Mitigation

### Option A: Standard rollback (no DB migration involved)

```bash
kubectl rollout undo deployment/<deployment> -n <namespace>
# Or to a specific known-good revision:
kubectl rollout undo deployment/<deployment> -n <namespace> --to-revision=<N>
kubectl rollout status deployment/<deployment> -n <namespace> --timeout=180s
```

### Option B: Canary failure — abort progressive rollout

```bash
# Argo Rollouts:
kubectl argo rollouts abort <rollout-name> -n <namespace>
# Scale down canary pods:
kubectl scale deployment/<deployment>-canary -n <namespace> --replicas=0
```

### Option C: Rollback WITH database migration (dangerous)

**⚠️ STOP: Do not rollback the application without addressing the migration.**

```bash
# 1. Check if migration is backward-compatible:
psql -U postgres -d <db> -c "\d <table>"
# 2. IF new column is non-nullable and old code doesn't populate it:
psql -U postgres -d <db> -c "
  ALTER TABLE <table> ALTER COLUMN <column> DROP NOT NULL;"
# 3. THEN rollback the application:
kubectl rollout undo deployment/<deployment> -n <namespace>
```

See [[INC-011-rollback-failed-frontend]] for a real example of this failure mode.

### Option D: Bad config rollout (ConfigMap/Secret error)

```bash
kubectl patch configmap <service>-config -n <namespace> \
  --type merge -p '{"data":{"<KEY>":"<correct-value>"}}'
kubectl rollout restart deployment/<deployment> -n <namespace>
```

### Option E: Feature flag caused the issue (no deployment rollback needed)

```bash
# Disable the flag in LaunchDarkly/Unleash/your flag system
# No pod restart needed if flag is polled dynamically
# Verify service recovers within 60 seconds of flag change
```

### Option F: ImagePullBackOff — ECR credentials expired

```bash
TOKEN=$(aws ecr get-login-password --region <region>)
kubectl create secret docker-registry regcred \
  --docker-server=<account>.dkr.ecr.<region>.amazonaws.com \
  --docker-username=AWS --docker-password=$TOKEN \
  -n <namespace> --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/<deployment> -n <namespace>
```

**After mitigation:** Monitor for 15 minutes — error rate at baseline, all pods stable, health endpoint returning 200.

## Verification

- [ ] All pods in `Running` state, 0 restarts in last 5 minutes
- [ ] Application error rate at pre-deployment baseline
- [ ] Health endpoint returning 200
- [ ] No new alerts in 15 minutes
- [ ] Rolled-back image tag matches expected version

```bash
kubectl get pods -n <namespace> -l app=<service-name>
kubectl get deploy <deployment> -n <namespace> \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
# Expected: last known good image tag
curl -s -o /dev/null -w "%{http_code}" https://<service-endpoint>/health
# Expected: 200
```

## Failure Signals

If the mitigation did NOT work, you will observe one or more of the following:

- Error rate does not decrease within 5 minutes of rollback
- Pods continue crashing after rollback (database schema incompatibility)
- ImagePullBackOff persists after credential refresh
- New error types appear that weren't present before the deployment
- Downstream services begin degrading

**If any failure signal is present after mitigation:** Do NOT repeat the same step. Proceed to Rollback or Escalation immediately.

## Rollback

If the rollback itself caused issues (e.g., rolled back too far, or DB is incompatible):

1. **Re-deploy the newer version (undo the undo):**
   ```bash
   kubectl rollout undo deployment/<deployment> -n <namespace>
   ```

2. **Or deploy a specific image tag:**
   ```bash
   kubectl set image deployment/<deployment> -n <namespace> \
     <container-name>=registry.internal/<service>:<specific-tag>
   ```

3. If a DB migration incompatibility was introduced by the rollback, engage DBA team immediately.

4. Notify #incident-response: "Rollback of rollback executed — escalating to DBA."

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Rollback does not reduce error rate within 10 min | Senior on-call + service owner | PagerDuty | 5 min response |
| Database migration involved in failed deploy | DBA team (required before any rollback) | #data-eng | Immediate |
| Cannot identify correct rollback revision | Release manager + service owner | #releases | 10 min response |
| Customer-facing SEV-1 with no fix in 20 min | Engineering Manager + IC | #incident-response | Immediate |
| Image pull failing cluster-wide | Platform team (credential/registry issue) | #platform-support | 10 min response |

## Notes

- **Always check for DB migrations before rolling back.** Rolling back application code without reverting the schema change causes constraint violations. See [[INC-011-rollback-failed-frontend]].
- **ConfigMap schema mismatches** are the #1 cause of canary failures in this environment. See [[INC-010-release-failed-canary-api]] — staging config was too simplified to catch the issue.
- **Feature flag issues don't need deployment rollback.** Disabling the flag is faster and safer. See [[INC-019-broken-feature-flag-auth]].
- **Zero-value config errors** can be catastrophic. See [[INC-020-bad-config-rollout-payment]] — rate limit set to `0` caused a retry storm.
- **ECR token expiry** is a silent killer — tokens expire after 12 hours. See [[INC-012-k8s-imagepullbackoff-reports]].
- **Canary deployments are your friend** — they limit blast radius. If canary caught the error, the rollback is simply aborting the rollout (no data risk).
- See also: [[INC-010-release-failed-canary-api]], [[INC-011-rollback-failed-frontend]]

## Maintenance

- **Last tested:** 2026-06-02
- **Review cycle:** Quarterly
- **Next review:** 2026-09-02
- **Test method:** Deploy a known-bad image tag in staging, execute full rollback procedure, verify recovery.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-02 | SRE Team | Initial publication |
| 2026-06-12 | SRE Team | Migrated to new runbook template format |
