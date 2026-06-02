<!-- File: RB-006-failed-deployment-rollback.md -->
---
id: RB-006
title: Failed Deployment Rollback (Kubernetes)
service_scope: all services
environment_scope: prod, staging
owner: SRE Team
severity_scope: high, critical
tags:
  - runbook
  - deployment
  - rollback
  - kubernetes
  - canary
  - config
  - prod
created: 2026-06-02
updated: 2026-06-02
related_incidents:
  - "[[INC-010-release-failed-canary-api]]"
  - "[[INC-011-rollback-failed-frontend]]"
  - "[[INC-019-broken-feature-flag-auth]]"
  - "[[INC-020-bad-config-rollout-payment]]"
  - "[[INC-012-k8s-imagepullbackoff-reports]]"
---

# Failed Deployment Rollback (Kubernetes)

## Trigger

- PagerDuty alert: `*-DeploymentFailed`, `*-CanaryErrorRate`, `*-RolloutStalled`
- Deployment pipeline: canary analysis failed, rollout paused or stuck
- Application error rate spike immediately after a deployment (5%+ error rate)
- Pods in `ImagePullBackOff`, `CrashLoopBackOff`, or `Error` state post-deploy
- User reports: new error type or broken feature appearing after release window

**Desired outcome:** Service running on last known good version with error rate at pre-deployment baseline.

## Preconditions

- [ ] `kubectl` access to affected cluster and namespace
- [ ] Knowledge of which deployment triggered the issue
- [ ] Access to deployment pipeline (Argo Rollouts, Flux, or CI/CD tool)
- [ ] Git access to service repository (for config/manifest review)
- [ ] Confirm whether the deployment included a database migration

**Required tools:** kubectl, git, deployment pipeline UI (Argo/Flux/Jenkins), Grafana

## Commands and Checks

### 1. Confirm the deployment state

```bash
kubectl rollout status deployment/<deployment> -n <namespace>
# IF not progressing → rollout is stuck
kubectl get pods -n <namespace> -l app=<service-name>
# Check pod states: Running, CrashLoopBackOff, ImagePullBackOff, Error
```

### 2. Check what changed in the latest rollout

```bash
kubectl rollout history deployment/<deployment> -n <namespace>
# Note the current revision number and previous revision
kubectl rollout history deployment/<deployment> -n <namespace> --revision=<current>
# Shows: image tag, env vars, resource changes
```

### 3. Check pod logs for crash reason

```bash
kubectl logs <new-pod-name> -n <namespace> --tail=100
# IF CrashLoopBackOff, check previous instance:
kubectl logs <pod-name> -n <namespace> --previous --tail=100
```

### 4. Check if it's an image pull issue

```bash
kubectl describe pod <pod-name> -n <namespace> | grep -A10 "Events"
# Look for: Failed to pull image, unauthorized, not found
# IF ImagePullBackOff → check ECR credentials, image tag existence
```

### 5. Check if a ConfigMap/Secret changed

```bash
kubectl get configmap <service>-config -n <namespace> -o yaml
# Compare with git — check for typos, zero values, schema mismatches
git diff HEAD~1 -- k8s/prod/<service>-config.yaml
```

### 6. CRITICAL: Check if a database migration was part of this deployment

```bash
# Check if the service runs migrations on startup:
kubectl logs <pod-name> -n <namespace> --previous | grep -i "migration\|flyway\|liquibase\|alembic"
# IF migration ran → rollback may be complex (see Scenario C below)
```

### 7. Check canary metrics (if using progressive delivery)

```bash
# Argo Rollouts:
kubectl argo rollouts get rollout <rollout-name> -n <namespace>
kubectl argo rollouts status <rollout-name> -n <namespace>
```

## Mitigation

### Scenario A: Standard rollback (no DB migration involved)

```bash
# Rollback to previous revision:
kubectl rollout undo deployment/<deployment> -n <namespace>
# Or to a specific known-good revision:
kubectl rollout undo deployment/<deployment> -n <namespace> --to-revision=<N>
# Wait for rollout to complete:
kubectl rollout status deployment/<deployment> -n <namespace> --timeout=180s
```

### Scenario B: Canary failure — abort progressive rollout

```bash
# Argo Rollouts:
kubectl argo rollouts abort <rollout-name> -n <namespace>
# Scale down canary pods:
kubectl scale deployment/<deployment>-canary -n <namespace> --replicas=0
# Verify all traffic back on stable pods:
kubectl get pods -n <namespace> -l app=<service-name>
```

### Scenario C: Rollback WITH database migration (dangerous)

**⚠️ STOP: Do not rollback the application without addressing the migration.**

1. Check if the migration is backward-compatible:
   ```bash
   psql -U postgres -d <db> -c "\d <table>"
   # Check: are new columns nullable? Does old code break with new schema?
   ```

2. IF migration added a non-nullable column that old code doesn't populate:
   ```bash
   # Make column nullable as an emergency fix:
   psql -U postgres -d <db> -c "
     ALTER TABLE <table> ALTER COLUMN <column> DROP NOT NULL;"
   ```

3. THEN rollback the application:
   ```bash
   kubectl rollout undo deployment/<deployment> -n <namespace>
   ```

4. See [[INC-011-rollback-failed-frontend]] for a real example of this failure mode.

### Scenario D: Bad config rollout (ConfigMap/Secret error)

```bash
# Fix the ConfigMap directly:
kubectl patch configmap <service>-config -n <namespace> \
  --type merge -p '{"data":{"<KEY>":"<correct-value>"}}'
# Restart pods to pick up change:
kubectl rollout restart deployment/<deployment> -n <namespace>
```

### Scenario E: Feature flag caused the issue (no deployment rollback needed)

```bash
# Disable the flag in LaunchDarkly/Unleash/your flag system
# No pod restart needed if flag is polled dynamically
# Verify service recovers within 60 seconds of flag change
```

### Scenario F: ImagePullBackOff — ECR credentials expired

```bash
# Regenerate ECR token:
TOKEN=$(aws ecr get-login-password --region <region>)
kubectl create secret docker-registry regcred \
  --docker-server=<account>.dkr.ecr.<region>.amazonaws.com \
  --docker-username=AWS --docker-password=$TOKEN \
  -n <namespace> --dry-run=client -o yaml | kubectl apply -f -
# Restart deployment to retry pull:
kubectl rollout restart deployment/<deployment> -n <namespace>
```

## Verification

- [ ] All pods in `Running` state, 0 restarts in last 5 minutes
- [ ] Application error rate at pre-deployment baseline
- [ ] Health endpoint returning 200
- [ ] No new alerts in 15 minutes
- [ ] Confirm rolled-back image tag matches expected version

```bash
kubectl get pods -n <namespace> -l app=<service-name>
kubectl get deploy <deployment> -n <namespace> \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
# Confirm this is the last known good image tag
curl -s -o /dev/null -w "%{http_code}" https://<service-endpoint>/health
# Expect: 200
```

## Rollback

If the rollback itself caused issues (e.g., rolled back too far, or DB is incompatible):

```bash
# Re-deploy the newer version (undo the undo):
kubectl rollout undo deployment/<deployment> -n <namespace>

# Or deploy a specific image tag:
kubectl set image deployment/<deployment> -n <namespace> \
  <container-name>=registry.internal/<service>:<specific-tag>
```

If a DB migration incompatibility was introduced by the rollback, engage DBA team immediately.

## Escalation

| Condition | Escalate to | Channel |
|-----------|-------------|---------|
| Rollback does not reduce error rate within 10 min | Senior on-call + service owner | PagerDuty |
| Database migration involved in failed deploy | DBA team required before any rollback | #data-eng |
| Cannot identify correct rollback revision | Release manager + service owner | #releases |
| Customer-facing SEV-1 with no fix in 20 min | Engineering Manager + IC | #incident-response |
| Image pull failing cluster-wide | Platform team (likely credential/registry issue) | #platform-support |

## Notes / Gotchas

- **Always check for DB migrations before rolling back.** Rolling back application code without reverting the schema change causes constraint violations. See [[INC-011-rollback-failed-frontend]].
- **ConfigMap schema mismatches** are the #1 cause of canary failures in this environment. See [[INC-010-release-failed-canary-api]] — staging config was too simplified to catch the issue.
- **Feature flag issues don't need deployment rollback.** Disabling the flag is faster and safer. See [[INC-019-broken-feature-flag-auth]].
- **Zero-value config errors** can be catastrophic. See [[INC-020-bad-config-rollout-payment]] — rate limit set to `0` caused a retry storm.
- **ECR token expiry** is a silent killer — tokens expire after 12 hours. See [[INC-012-k8s-imagepullbackoff-reports]].
- **Canary deployments are your friend** — they limit blast radius. If canary caught the error, the rollback is simply aborting the rollout (no data risk).
