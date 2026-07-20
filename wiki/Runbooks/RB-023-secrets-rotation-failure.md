---
id: RB-023
title: Secrets Rotation Failure and Credential Sync Recovery
service: "*"
related_services:
  - vault
  - aws-secrets-manager
  - auth-service
  - payment-service
severity: SEV-1
environment: prod
category: connectivity
risk_level: high
estimated_duration: "20m"
approval_required: yes
approver_role: Security Lead
tags:
  - runbook
  - secrets
  - rotation
  - credentials
  - vault
  - aws
  - prod
related_incidents:
  - "[[INC-056-oauth-token-signing-key-rotation-failure]]"
  - "[[INC-070-secrets-manager-rotation-lambda-timeout]]"
  - "[[INC-038-vault-seal-auto-unseal-failure]]"
related_runbooks:
  - "[[RB-012-vault-sealed-recovery]]"
related_guardrails: []
---

## Purpose

Recover from failed secret rotation that leaves credentials out of sync between the secret store and the consuming service or database.

**Desired outcome:** Credentials in sync — application using current valid credential, previous credential still accepted for transition period.

## Success Criteria

- Application authenticating successfully to all backends
- Secret store showing rotation completed (not stuck in-progress)
- No `authentication failed` errors in application logs
- Both old and new credentials valid during transition window

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any service depending on rotated credentials |
| Related services | vault, aws-secrets-manager, auth-service, payment-service |
| Environments | prod |
| Use when | `*-CredentialRotationFailed`, application auth failures after rotation window |
| Do NOT use when | Application has wrong static credentials (config error, not rotation) |
| Risk level | High (wrong fix can lock out services from databases) |
| Estimated duration | 15–20 minutes |
| Approval required | Yes — Security Lead |

## Prerequisites

- [ ] Access to secret store (Vault/AWS Secrets Manager)
- [ ] Database admin access (to verify/set credentials)
- [ ] Knowledge of which credential is out of sync
- [ ] Security Lead approval

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `vault` CLI or AWS CLI | Secret store operations | Admin |
| `psql`/`mysql` | Database credential verification | DBA |
| `kubectl` | Application pod operations | Cluster admin |

## Trigger

- Alert: `*-CredentialRotationFailed`, `*-DBAuthFailed`
- Symptom: Application logging `authentication failed` after rotation window
- Symptom: Secret store showing rotation "IN_PROGRESS" for >10 min
- Symptom: Vault/Secrets Manager rotation Lambda timeout

## Triage

1. Identify which credential failed
   ```bash
   kubectl logs -l app=<service> -n <namespace> --tail=50 | grep -i "auth.*failed\|password.*incorrect"
   ```

2. Check rotation status in secret store
   ```bash
   # AWS Secrets Manager:
   aws secretsmanager describe-secret --secret-id <secret-id> | jq '.RotationEnabled,.LastRotatedDate'
   # Vault:
   vault read <secret-path>
   ```

3. Determine which step failed (set new password in DB vs. update in store)

## Investigation

1. **Check if new password is set in database**
   ```bash
   # Try authenticating with AWSPENDING version:
   aws secretsmanager get-secret-value --secret-id <id> --version-stage AWSPENDING
   # Try connecting to DB with that password
   psql -U <user> -h <host> -d <db>
   ```

2. **Check if application is using old or new credential**
   ```bash
   kubectl exec <pod> -n <namespace> -- env | grep DB_PASSWORD
   # Or check mounted secret age
   ```

3. **Decision point:**
   - IF DB has new password but app has old → proceed to Mitigation Option A
   - IF DB has old password but store shows new → proceed to Mitigation Option B
   - IF rotation stuck in-progress → proceed to Mitigation Option C

## Mitigation

### Option A: Sync app to new credential

```bash
# Restart pods to pick up new secret value:
kubectl rollout restart deployment/<service> -n <namespace>
# If using external-secrets operator, force sync:
kubectl annotate externalsecret <name> -n <namespace> force-sync=$(date +%s)
```

### Option B: Revert DB to old credential

```bash
# Get the old (AWSCURRENT) credential:
aws secretsmanager get-secret-value --secret-id <id> --version-stage AWSCURRENT | jq -r '.SecretString'
# Reset DB password back:
psql -U postgres -c "ALTER USER <user> PASSWORD '<old-password>';"
# Cancel the rotation:
aws secretsmanager cancel-rotate-secret --secret-id <id>
```

### Option C: Complete stuck rotation manually

```bash
# Promote AWSPENDING to AWSCURRENT:
aws secretsmanager update-secret-version-stage --secret-id <id> \
  --version-stage AWSCURRENT \
  --move-to-version-id <pending-version-id> \
  --remove-from-version-id <current-version-id>
# Restart application:
kubectl rollout restart deployment/<service> -n <namespace>
```

**After mitigation:** Verify application can authenticate to all backends.

## Verification

- [ ] Application logs: no auth errors for 5 minutes
- [ ] `kubectl exec` test: can connect to DB with current credential
- [ ] Secret store: rotation not stuck
- [ ] Service health endpoint returning 200

```bash
kubectl logs -l app=<service> -n <namespace> --tail=20 | grep -c "auth.*failed"
# Expected: 0
```

## Failure Signals

- Application still failing auth after restart
- DB not accepting any known credential
- Multiple services affected (shared credential)

**If any failure signal is present:** Escalate to DBA + Security immediately.

## Rollback

1. **If you set wrong password in DB:** Reset to known backup credential
2. **If you promoted wrong secret version:** Roll back version stage

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Cannot determine correct credential | DBA + Security | PagerDuty P1 | Immediate |
| Multiple services locked out | EM + Security Lead | #incident-response | Immediate |
| Potential credential exposure | SecOps | #security-urgent | Immediate |

## Notes

- **Rotation must be additive:** Set new password, verify app can use it, THEN revoke old one.
- **Never revoke old credential before confirming new one works.** See [[INC-056-oauth-token-signing-key-rotation-failure]].
- **Rotation Lambda timeouts** are the #1 cause of stuck rotations. See [[INC-070-secrets-manager-rotation-lambda-timeout]].
- **JVM services cache credentials** — restart required to pick up new values.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Monthly
- **Next review:** 2026-07-15
- **Test method:** Trigger secret rotation in staging, verify application handles transition.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Security Team + SRE | Initial publication |
