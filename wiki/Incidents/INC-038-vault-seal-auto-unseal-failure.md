---
id: INC-038
title: HashiCorp Vault Sealed After Auto-Unseal KMS Key Rotation
severity: SEV-1
service: vault
environment: prod
category: outage
date: 2026-03-12
duration: "52m"
detection_gap: "6m"
tags:
  - incident
  - vault
  - secrets
  - kms
  - aws
  - critical
  - prod
  - security
---

## Summary

At 02:14 UTC on 2026-03-12, the production Vault cluster sealed itself after the AWS KMS auto-unseal key was rotated by an automated key rotation policy. The new key version was not authorized in the Vault configuration, causing all 3 Vault nodes to seal on their next restart (triggered by a routine pod recycling). All services depending on dynamic secrets (DB credentials, API keys) began failing within minutes.

## Symptoms

- PagerDuty: `Vault-Sealed` at 02:20 UTC
- Vault API: HTTP 503 `Vault is sealed` on all endpoints
- auth-service, payment-service, reporting-service: `VAULT_ERR: secret not found` errors
- New pod startups failing: unable to fetch secrets from Vault init containers
- All secret-dependent deployments entering CrashLoopBackOff

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All users (~22,000 active) — authentication and payments down |
| Services degraded | vault (sealed), auth-service, payment-service, reporting-service, all new pods |
| Revenue impact | ~$48K in failed transactions |
| Duration | 02:14 → 03:06 UTC (52 min) |
| Data loss | None |
| SLA breach | Yes — multiple services breached SLA |
| Customer comms | Status page updated at 02:25 UTC, customer email at 03:00 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 02:00 | AWS KMS automatic key rotation executed for vault-unseal-key |
| 02:14 | Vault pod recycled by cluster autoscaler, sealed on restart |
| 02:15 | Remaining 2 Vault pods lost quorum, all sealed |
| 02:20 | Alert fired: `Vault-Sealed` |
| 02:22 | On-call acknowledged (Raj Patel) |
| 02:35 | KMS key rotation identified as cause |
| 02:48 | KMS key policy updated to include new key version |
| 02:52 | Vault manually unsealed |
| 03:00 | Services began recovering as secrets became available |
| 03:06 | All services healthy, incident closed |

## Diagnosis

1. Confirmed Vault seal status
   ```bash
   kubectl exec vault-0 -n vault -- vault status
   # Sealed: true, Type: awskms
   ```

2. Checked Vault logs for unseal error
   ```bash
   kubectl logs vault-0 -n vault --tail=50
   # [ERROR] core: failed to unseal: err="error decrypting seal key: AccessDeniedException: The ciphertext refers to a customer master key that does not exist"
   ```

3. Confirmed KMS key rotation via CloudTrail
   ```bash
   aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=RotateKey --max-results 5
   # RotateKey event at 02:00 UTC for key alias/vault-unseal-key
   ```

4. Vault config referenced the key by alias (which now points to new version) but the encrypted seal key was encrypted with the old version

## Resolution

1. **Mitigate:** Updated KMS key policy to allow decryption with previous key versions
   ```bash
   aws kms update-key-policy --key-id alias/vault-unseal-key --policy file://updated-policy.json
   ```

2. **Fix:** Manually unsealed Vault
   ```bash
   kubectl exec vault-0 -n vault -- vault operator unseal -migrate
   ```

3. **Verify:** Confirmed all services recovering
   ```bash
   kubectl exec vault-0 -n vault -- vault status
   # Sealed: false, HA Mode: active
   kubectl get pods --all-namespaces | grep -c CrashLoopBackOff
   # 0
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Vault sealed in prod | Page on-call + security team immediately | PagerDuty P1 |
| Cannot unseal within 15 min | Page EM + platform lead | #incident-response |
| Secrets compromised suspected | Engage SecOps | #security-urgent |

## Post-Incident Review

**What went well:**
- Vault seal alert fired quickly
- Team had documented unseal procedure

**What needs improvement:**
- KMS automatic key rotation not tested with Vault auto-unseal
- No pre-rotation validation that Vault can still unseal
- Pod recycling during key rotation window created the trigger

**Contributing factors (beyond root cause):**
- AWS KMS automatic rotation enabled without Vault team awareness
- Vault configuration did not handle key version changes gracefully
- Cluster autoscaler recycled a Vault pod at the worst possible time

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Unseal Vault, restore services | Raj Patel | 2026-03-12 | Done |
| Disable automatic KMS rotation, switch to manual with Vault validation | Security team | 2026-03-19 | Open |
| Add pre-rotation runbook step: verify Vault can unseal with new key | SRE team | 2026-03-19 | Open |
| Exclude Vault pods from autoscaler eviction | Platform team | 2026-03-19 | Open |
| Test Vault unseal after KMS rotation quarterly | SRE team | 2026-03-26 | Open |

## Links

- Runbooks: [[RB-012-vault-sealed-recovery]]
- Related incidents: None
- PR/commit: N/A
- Post-mortem doc: N/A
