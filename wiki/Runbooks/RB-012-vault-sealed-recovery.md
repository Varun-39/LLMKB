---
id: RB-012
title: Vault Sealed Recovery and Secret Management Outage
service: vault
related_services:
  - auth-service
  - payment-service
  - all-services
severity: SEV-1
environment: prod
category: connectivity
risk_level: high
estimated_duration: "20m"
approval_required: yes
approver_role: Security Lead
tags:
  - runbook
  - vault
  - secrets
  - sealed
  - kms
  - prod
related_incidents:
  - "[[INC-038-vault-seal-auto-unseal-failure]]"
  - "[[INC-070-secrets-manager-rotation-lambda-timeout]]"
related_runbooks:
  - "[[RB-007-pod-crash-investigation]]"
related_guardrails: []
---

## Purpose

Recover from a sealed Vault cluster, covering KMS auto-unseal failures, manual unseal procedures, and restoring secret access to dependent services.

**Desired outcome:** Vault unsealed, HA mode active, all services able to read secrets without errors.

## Success Criteria

- `vault status` shows `Sealed: false`
- HA mode: active (leader elected)
- All dependent services fetching secrets successfully
- No CrashLoopBackOff pods due to missing secrets
- Vault audit log recording operations

## Scope

| Attribute | Value |
|-----------|-------|
| Service | vault |
| Related services | auth-service, payment-service, all secret-dependent services |
| Environments | prod |
| Use when | `Vault-Sealed` alert, services failing with secret fetch errors |
| Do NOT use when | Vault is unsealed but returning permission errors (policy issue) |
| Risk level | High (secrets management is critical infrastructure) |
| Estimated duration | 15–20 minutes |
| Approval required | Yes — Security Lead |

## Prerequisites

- [ ] Access to Vault pods/nodes
- [ ] KMS key access (for auto-unseal troubleshooting)
- [ ] Unseal keys or recovery keys (for manual unseal)
- [ ] Security Lead approval confirmed

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `vault` CLI | Status, unseal, diagnostics | Vault admin token |
| `kubectl` | Pod operations | Cluster admin |
| AWS Console/CLI | KMS key diagnostics | IAM admin |
| `jq` | JSON parsing | Local tool |

## Trigger

- Alert: `Vault-Sealed`
- Symptom: Services logging `VAULT_ERR: secret not found` or `connection refused on 8200`
- Symptom: New pods failing to start (init container fetching secrets fails)
- Metric: Vault health endpoint returning 503

## Triage

1. Confirm Vault seal status
   ```bash
   kubectl exec vault-0 -n vault -- vault status
   # What to look for: Sealed: true/false, Type: shamir/awskms
   ```

2. Assess blast radius — which services are affected
   ```bash
   kubectl get pods --all-namespaces | grep -E "CrashLoop|Init:Error"
   # What to look for: pods failing due to secret fetch
   ```

3. Check if auto-unseal KMS key is accessible
   ```bash
   aws kms describe-key --key-id alias/vault-unseal-key
   # What to look for: KeyState should be "Enabled"
   ```

## Investigation

1. **Check Vault logs for seal reason**
   ```bash
   kubectl logs vault-0 -n vault --tail=100 | grep -i "seal\|error\|kms"
   ```

2. **Check KMS key permissions**
   ```bash
   aws kms list-grants --key-id alias/vault-unseal-key | jq '.Grants[] | select(.GranteePrincipal | contains("vault"))'
   ```

3. **Check if Vault pods were restarted (lost in-memory unseal state)**
   ```bash
   kubectl get pods -n vault -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}'
   ```

4. **Decision point:**
   - IF KMS key issue → proceed to Mitigation Option A
   - IF manual unseal needed (shamir) → proceed to Mitigation Option B
   - IF Vault pod crash loop → proceed to Mitigation Option C

## Mitigation

### Option A: Fix KMS auto-unseal

```bash
# Verify KMS key policy allows Vault role:
aws kms get-key-policy --key-id alias/vault-unseal-key --policy-name default
# If policy is wrong, update it:
aws kms put-key-policy --key-id alias/vault-unseal-key --policy-name default --policy file://vault-kms-policy.json
# Restart Vault to retry auto-unseal:
kubectl delete pod vault-0 -n vault
```

### Option B: Manual unseal (shamir keys)

```bash
# Requires threshold number of unseal keys (typically 3 of 5):
kubectl exec vault-0 -n vault -- vault operator unseal <key-1>
kubectl exec vault-0 -n vault -- vault operator unseal <key-2>
kubectl exec vault-0 -n vault -- vault operator unseal <key-3>
# Repeat for other Vault pods in HA cluster
```

### Option C: Vault pod crash — fix and restart

```bash
kubectl describe pod vault-0 -n vault
# Fix underlying issue (disk, memory, network), then:
kubectl delete pod vault-0 -n vault
# If auto-unseal configured, it will unseal on startup
```

**After mitigation:** Verify all dependent services can read secrets.

## Verification

- [ ] `vault status` shows `Sealed: false`
- [ ] HA mode active, leader elected
- [ ] Services reading secrets successfully
- [ ] No CrashLoopBackOff pods
- [ ] Vault audit log active

```bash
kubectl exec vault-0 -n vault -- vault status
# Sealed: false, HA Mode: active
kubectl get pods --all-namespaces | grep -c CrashLoop
# Expected: 0
```

## Failure Signals

- Vault seals again immediately after unseal
- KMS key permanently inaccessible
- Data corruption in Vault storage backend
- HA peers cannot discover each other

**If any failure signal is present:** Escalate immediately.

## Rollback

1. **If unseal attempt corrupts state:** Restore from Vault snapshot
2. **If KMS key rotation broke access:** Contact AWS support for key recovery

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Cannot unseal within 15 min | Security Lead + Platform | PagerDuty P1 | Immediate |
| KMS key inaccessible | AWS support + Security | Support case | 10 min |
| Vault data corruption | Security Lead + CTO | #incident-response | Immediate |
| All services down due to missing secrets | EM + IC | PagerDuty P1 | Immediate |

## Notes

- **Auto-unseal does not survive KMS key deletion.** If the key is deleted, Vault is permanently sealed without recovery keys.
- **Always test KMS key rotation with Vault** before enabling automatic rotation.
- **Keep recovery keys in a separate, secure location** (not in Vault itself).
- See [[INC-038-vault-seal-auto-unseal-failure]] for real-world KMS rotation failure.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Monthly
- **Next review:** 2026-07-15
- **Test method:** Seal Vault in staging, execute unseal procedure, verify service recovery.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Security Team + SRE | Initial publication |
