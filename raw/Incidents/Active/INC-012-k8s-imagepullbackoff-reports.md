---
id: INC-012
title: ImagePullBackOff on reporting-service — ECR Credential Expiry
severity: SEV-2
service: reporting-service
environment: prod
category: deployment-failure
status: resolved
owner: James Okafor
assigned-to: James Okafor
date: 2026-04-08
duration: 31 minutes
created: 2026-04-08
updated: 2026-04-08
tags:
  - incident
  - kubernetes
  - imagepull
  - container
  - high
  - prod
  - reporting
related_runbooks:
  - "[[RB-006-pod-crash]]"
  - "[[RB-005-failed-deployment]]"
related_incidents:
  - "[[INC-010-release-failed-canary-api]]"
---

# INC-012 — ImagePullBackOff on reporting-service: ECR Credential Expiry

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

## Possible Causes

1. **Expired ECR token in regcred Secret** — ECR tokens expire after 12 hours; automated rotation job had not run since 2026-04-07 16:00 UTC
2. **Cron job failure** — `ecr-token-rotator` CronJob failed silently overnight
3. **IAM role misconfiguration** — instance role lost ECR read permissions after an IAM policy update
4. **Wrong secret referenced** — deployment spec pointed to `regcred-legacy` instead of current `regcred`

## Troubleshooting Steps

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

1. Manually regenerated ECR token and updated Secret
   ```bash
   TOKEN=$(aws ecr get-login-password --region us-east-1)
   kubectl create secret docker-registry regcred \
     --docker-server=<account>.dkr.ecr.us-east-1.amazonaws.com \
     --docker-username=AWS \
     --docker-password=$TOKEN \
     -n reporting --dry-run=client -o yaml | kubectl apply -f -
   ```

2. Restarted the stalled rollout
   ```bash
   kubectl rollout restart deployment/reporting-service -n reporting
   kubectl rollout status deployment/reporting-service -n reporting --timeout=120s
   ```

3. Fixed IAM policy to restore `ecr:GetAuthorizationToken` permission (PR #infra-441)

4. Confirmed rotator CronJob ran successfully on next cycle
   ```bash
   kubectl get jobs -n infra | grep ecr-token-rotator
   # Completed
   ```

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Deployment stalled >15 min in prod | Page on-call SRE | PagerDuty |
| Image pull failing across multiple namespaces | Escalate to infra team — cluster-wide credential issue | #platform-support |
| Old pods terminating with no new pods Ready | Declare SEV-1, halt further rollouts | #incident-response |

## Post-Incident Notes

**Went well:**
- Old pods continued serving — no customer impact
- Root cause traced quickly via CronJob logs

**Improve:**
- ECR token rotator failure was silent — no alert on CronJob failure
- IAM policy change had no downstream impact analysis before applying

**Action items:**
- [x] Rotated ECR credentials, resumed deployment
- [x] Restored IAM policy permission
- [ ] Add alert for CronJob failure (any job in Failed state in `infra` namespace)
- [ ] Add IAM policy change review step that checks dependent service accounts
- [ ] Consider using IRSA (IAM Roles for Service Accounts) to eliminate static token rotation

## Related Runbooks

- [[RB-006-pod-crash]]
- [[RB-005-failed-deployment]]
