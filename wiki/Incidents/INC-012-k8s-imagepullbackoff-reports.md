---
id: INC-012
title: ImagePullBackOff on reporting-service — ECR Credential Expiry
severity: SEV-2
service: reporting-service
environment: prod
category: deployment-failure
date: 2026-04-08
duration: "31m"
detection_gap: "4m"
tags:
  - incident
  - kubernetes
  - imagepull
  - container
  - high
  - prod
  - reporting
error_family: imagepullbackoff
resolution_runbook: RB-006
resolution_outcome: resolved
---

## Summary

A scheduled reporting-service deployment at 06:00 UTC on 2026-04-08 left all new pods in `ImagePullBackOff` state. The ECR pull-through cache credentials stored in the `regcred` Kubernetes Secret had expired 12 hours earlier, silently preventing image pulls. Existing pods continued running on the old image; no service disruption occurred, but the deployment was stalled for 31 minutes until credentials were rotated and the rollout resumed.

## Symptoms

- Deployment pipeline alert: `reporting-service-rollout-stalled` at 06:04 UTC
- `kubectl get pods -n reporting` showed new pods cycling between `Init:ImagePullBackOff` and `ErrImagePull`
- Pod events: `Failed to pull image: unauthorized: authentication required`
- No customer-facing impact — old pods still serving traffic
- Grafana deployment dashboard: rollout progress frozen at 0/4 new pods

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | None — old pods continued serving |
| Services degraded | reporting-service deployment blocked (no new version running) |
| Revenue impact | None directly; delayed feature release |
| Duration | 06:00 → 06:31 UTC (31 min) |
| Data loss | None |
| SLA breach | No — no user-facing impact |
| Customer comms | N/A — no impact |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 06:00 | Scheduled deployment triggered for reporting-service |
| 06:01 | New pods enter ImagePullBackOff state |
| 06:04 | Alert fired: `reporting-service-rollout-stalled` |
| 06:06 | On-call acknowledged (James Okafor) |
| 06:10 | ECR credential expiry identified as root cause |
| 06:15 | Token rotator CronJob failure traced to IAM policy change |
| 06:20 | Manual ECR token regenerated, secret updated |
| 06:25 | Rollout restarted, new pods pulling successfully |
| 06:31 | Deployment complete, incident closed |

## Diagnosis

1. Confirmed ImagePullBackOff state and inspected events
   ```bash
   kubectl get pods -n reporting -l app=reporting-service
   # 4 new pods: ImagePullBackOff
   kubectl describe pod reporting-svc-7f8d-rp01 -n reporting | grep -A10 "Events"
   # Failed to pull image: unauthorized: authentication required
   ```

2. Verified the ECR secret token age
   ```bash
   kubectl get secret regcred -n reporting -o jsonpath='{.metadata.creationTimestamp}'
   # 2026-04-07T05:31:00Z  — over 24 hours old (expired after 12h)
   ```

3. Checked the token rotator CronJob
   ```bash
   kubectl get cronjob ecr-token-rotator -n infra
   kubectl get jobs -n infra | grep ecr-token-rotator
   # Last job: 2026-04-07T16:00:00Z — Status: Failed
   ```

4. Reviewed rotator job logs
   ```bash
   kubectl logs job/ecr-token-rotator-28521120 -n infra
   # Error: AccessDeniedException — ecr:GetAuthorizationToken not authorized
   ```

5. Identified root cause: IAM role policy updated 2026-04-07 15:45 UTC removed `ecr:GetAuthorizationToken` from the rotator's service account role

## Resolution

1. **Mitigate:** Manually regenerated ECR token and updated Secret
   ```bash
   TOKEN=$(aws ecr get-login-password --region us-east-1)
   kubectl create secret docker-registry regcred \
     --docker-server=<account>.dkr.ecr.us-east-1.amazonaws.com \
     --docker-username=AWS \
     --docker-password=$TOKEN \
     -n reporting --dry-run=client -o yaml | kubectl apply -f -
   ```

2. **Fix:** Restarted the stalled rollout and fixed IAM policy (PR #infra-441)
   ```bash
   kubectl rollout restart deployment/reporting-service -n reporting
   kubectl rollout status deployment/reporting-service -n reporting --timeout=120s
   ```

3. **Verify:** Confirmed rotator CronJob ran successfully on next cycle
   ```bash
   kubectl get jobs -n infra | grep ecr-token-rotator
   # Completed
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Deployment stalled >15 min in prod | Page on-call SRE | PagerDuty |
| Image pull failing across multiple namespaces | Escalate to infra team — cluster-wide credential issue | #platform-support |
| Old pods terminating with no new pods Ready | Declare SEV-1, halt further rollouts | #incident-response |

## Post-Incident Review

**What went well:**
- Old pods continued serving — no customer impact
- Root cause traced quickly via CronJob logs

**What needs improvement:**
- ECR token rotator failure was silent — no alert on CronJob failure
- IAM policy change had no downstream impact analysis before applying

**Contributing factors (beyond root cause):**
- IAM policy update removed `ecr:GetAuthorizationToken` without impact analysis
- CronJob failure alerting not configured for `infra` namespace
- No monitoring on secret age/expiry

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Rotate ECR credentials, resume deployment | James Okafor | 2026-04-08 | Done |
| Restore IAM policy permission | James Okafor | 2026-04-08 | Done |
| Add alert for CronJob failure in `infra` namespace | SRE team | 2026-04-22 | Open |
| Add IAM policy change review step for dependent service accounts | Platform team | 2026-04-22 | Open |
| Consider using IRSA to eliminate static token rotation | Platform team | 2026-05-06 | Open |

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]], [[RB-007-pod-crash-investigation]]
- Related incidents: [[INC-010-release-failed-canary-api]]
- PR/commit: PR #infra-441 (IAM policy fix)
- Post-mortem doc: N/A
