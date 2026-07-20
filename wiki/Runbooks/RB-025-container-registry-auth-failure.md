---
id: RB-025
title: Container Registry Authentication Failure (ECR/Docker)
service: "*"
related_services:
  - ci-cd
  - all-deployments
severity: SEV-2
environment: prod
category: deployment
risk_level: medium
estimated_duration: "10m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - ecr
  - docker
  - registry
  - imagepull
  - kubernetes
  - prod
related_incidents:
  - "[[INC-012-k8s-imagepullbackoff-reports]]"
  - "[[INC-034-github-actions-runner-token-expiry]]"
related_runbooks:
  - "[[RB-006-failed-deployment-rollback]]"
  - "[[RB-007-pod-crash-investigation]]"
related_guardrails: []
---

## Purpose

Resolve container image pull failures caused by expired registry credentials, missing image tags, or registry authentication issues.

**Desired outcome:** All pods able to pull images successfully, deployments proceeding normally.

## Success Criteria

- No pods in `ImagePullBackOff` or `ErrImagePull` state
- New deployments pulling images successfully
- Registry credentials valid (not expired)
- CI/CD pipelines pushing images without auth errors

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any service with image pull failures |
| Related services | ci-cd, all deployments |
| Environments | prod, staging |
| Use when | `ImagePullBackOff`, `ErrImagePull`, or `unauthorized` errors in pod events |
| Do NOT use when | Image exists but pod crashes after pull (application issue) |
| Risk level | Medium |
| Estimated duration | 5–10 minutes |
| Approval required | No |

## Prerequisites

- [ ] AWS CLI access (for ECR token refresh)
- [ ] `kubectl` access to affected namespace
- [ ] Knowledge of which registry and image is failing

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Pod event inspection | Cluster admin |
| AWS CLI | ECR token generation | IAM write |
| `docker` CLI | Manual pull test | Local |

## Trigger

- Pod events: `Failed to pull image: unauthorized` or `ImagePullBackOff`
- Deployments stuck with new pods unable to start
- CI/CD: `docker push` failing with 401

## Triage

1. Confirm image pull error
   ```bash
   kubectl describe pod <pod-name> -n <namespace> | grep -A5 "Events"
   # What to look for: "unauthorized", "not found", "ImagePullBackOff"
   ```

2. Determine error type
   ```bash
   # unauthorized = credential issue → Option A
   # not found = wrong image tag → Option B
   # manifest unknown = tag doesn't exist in registry → Option B
   ```

## Mitigation

### Option A: Refresh ECR credentials

```bash
# ECR tokens expire after 12 hours. Regenerate:
TOKEN=$(aws ecr get-login-password --region <region>)
kubectl create secret docker-registry regcred \
  --docker-server=<account>.dkr.ecr.<region>.amazonaws.com \
  --docker-username=AWS \
  --docker-password=$TOKEN \
  -n <namespace> --dry-run=client -o yaml | kubectl apply -f -
# Restart failed pods:
kubectl delete pods -n <namespace> --field-selector=status.phase=Pending
```

### Option B: Fix image reference

```bash
# Check if image exists:
aws ecr describe-images --repository-name <repo> --image-ids imageTag=<tag>
# If not found, fix deployment image:
kubectl set image deployment/<name> -n <namespace> <container>=<correct-image:tag>
```

### Option C: Fix imagePullSecret reference on ServiceAccount

```bash
kubectl patch serviceaccount default -n <namespace> \
  -p '{"imagePullSecrets": [{"name": "regcred"}]}'
kubectl rollout restart deployment/<name> -n <namespace>
```

**After mitigation:** Verify pods start pulling images.

## Verification

- [ ] No pods in ImagePullBackOff
- [ ] New pods starting successfully
- [ ] `kubectl describe pod` shows successful pull

```bash
kubectl get pods -n <namespace> | grep -E "ImagePull|ErrImage"
# Expected: empty
```

## Failure Signals

- Token refresh doesn't fix auth error (IAM role issue)
- Image genuinely doesn't exist (CI didn't push)
- Registry endpoint unreachable (network issue)

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| IAM role cannot authenticate to ECR | Platform team | #platform-support | 10 min |
| Registry completely unreachable | AWS support | Support case | 15 min |
| CI/CD not pushing images | Release team | #releases | 10 min |

## Notes

- **ECR tokens expire after 12 hours.** Use a CronJob or controller to auto-refresh.
- **IRSA (IAM Roles for Service Accounts)** eliminates the need for explicit pull secrets in EKS.
- **Check all namespaces** — the regcred secret must exist in each namespace where pods pull images.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Monthly
- **Next review:** 2026-07-15
- **Test method:** Let ECR token expire in staging, execute refresh procedure.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
