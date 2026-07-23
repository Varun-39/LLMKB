---
id: INC-070
title: Secrets Manager Rotation Lambda Timeout — DB Password Out of Sync
severity: SEV-1
service: auth-service
environment: prod
category: outage
date: 2026-06-18
duration: "30m"
tags:
  - incident
  - aws
  - secrets-manager
  - rotation
  - lambda
  - database
  - critical
  - prod
error_family: unknown
resolution_runbook: RB-012
resolution_outcome: resolved
---

## Summary

The AWS Secrets Manager rotation Lambda for the auth-service database credentials timed out mid-rotation after the "setSecret" step but before the "finishSecret" step. The new password was set in Postgres, but Secrets Manager still reported the old password as the "current" version. All auth-service pods using the cached old password could no longer authenticate to the database.

## Symptoms

- PagerDuty: `AuthService-DBAuthFailed` at 04:05 UTC
- auth-service logs: `FATAL: password authentication failed for user "auth_app"`
- AWS Secrets Manager: rotation status "IN_PROGRESS" (stuck)
- Lambda: timed out after 300s during `finishSecret` step
- All auth operations failed

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | 100% of users (~28,000 active) — login/signup broken |
| Services degraded | auth-service (DB auth failed) |
| Revenue impact | ~$35K in lost transactions |
| Duration | 04:05 → 04:35 UTC (30 min) |
| Data loss | None |
| SLA breach | Yes — auth SLA breached |
| Customer comms | Status page updated at 04:10 UTC |

## Diagnosis

1. Confirmed DB auth failure
   ```bash
   kubectl logs -l app=auth-service -n auth --tail=20
   # FATAL: password authentication failed for user "auth_app"
   ```

2. Checked Secrets Manager rotation status
   ```bash
   aws secretsmanager describe-secret --secret-id prod/auth-db
   # RotationEnabled: true, LastRotationStatus: "IN_PROGRESS"
   # VersionIdsToStages: AWSCURRENT → old version, AWSPENDING → new version (password already set in DB)
   ```

3. Lambda CloudWatch logs: timeout at 300s during `finishSecret` (network issue to Secrets Manager API)

## Resolution

1. **Mitigate:** Manually completed the rotation by promoting AWSPENDING to AWSCURRENT
   ```bash
   aws secretsmanager update-secret-version-stage --secret-id prod/auth-db \
     --version-stage AWSCURRENT --move-to-version-id <pending-version-id> \
     --remove-from-version-id <old-version-id>
   ```

2. **Fix:** Restarted auth-service to pick up new secret
   ```bash
   kubectl rollout restart deployment/auth-service -n auth
   ```

3. **Verify:** Auth operations working with new password

## Post-Incident Review

- Rotation Lambda timeout left credentials in inconsistent state
- Increased Lambda timeout from 300s to 900s
- Added monitoring: alert if rotation status is "IN_PROGRESS" for >10 minutes
- Added fallback: auth-service tries both AWSCURRENT and AWSPENDING passwords
- Added VPC endpoint for Secrets Manager to avoid NAT gateway timeouts

## Links

- Runbooks: [[RB-012-vault-sealed-recovery]]
- Related incidents: [[INC-038-vault-seal-auto-unseal-failure]]
