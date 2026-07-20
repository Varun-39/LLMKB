---
id: RB-016
title: Terraform State Recovery and Lock Remediation
service: infrastructure
related_services:
  - ci-cd
  - all-services
severity: SEV-3
environment: prod
category: deployment
risk_level: high
estimated_duration: "20m"
approval_required: yes
approver_role: Infrastructure Lead
tags:
  - runbook
  - terraform
  - state
  - infrastructure
  - ci-cd
  - prod
related_incidents:
  - "[[INC-025-terraform-state-lock-contention]]"
  - "[[INC-037-s3-bucket-policy-deny-all]]"
related_runbooks:
  - "[[RB-006-failed-deployment-rollback]]"
related_guardrails: []
---

## Purpose

Recover from Terraform state lock contention, state corruption, and state drift issues that block infrastructure changes.

**Desired outcome:** Terraform state unlocked, consistent with actual infrastructure, and CI/CD pipelines able to plan/apply.

## Success Criteria

- `terraform plan` completes without errors
- No state lock held (DynamoDB lock table clear)
- State matches actual infrastructure (no unexpected drift)
- CI/CD pipelines running successfully

## Scope

| Attribute | Value |
|-----------|-------|
| Service | infrastructure (Terraform) |
| Related services | ci-cd, all services managed by Terraform |
| Environments | prod, staging |
| Use when | `terraform plan/apply` failing with state lock or corruption errors |
| Do NOT use when | Terraform syntax/validation errors (fix the code) |
| Risk level | High (state manipulation can cause resource deletion) |
| Estimated duration | 15–20 minutes |
| Approval required | Yes — Infrastructure Lead |

## Prerequisites

- [ ] Terraform CLI access with backend credentials
- [ ] AWS access to DynamoDB lock table and S3 state bucket
- [ ] Knowledge of which state file is affected
- [ ] Backup of state file verified

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `terraform` CLI | State operations | Backend write access |
| AWS CLI | DynamoDB lock table, S3 state bucket | Write access |
| Git | Infrastructure code repository | Read access |

## Trigger

- CI/CD failure: `Error acquiring the state lock`
- CI/CD failure: `Error loading state: state data is not valid`
- Symptom: All Terraform pipelines blocked
- Symptom: `terraform plan` shows unexpected destroy/recreate

## Triage

1. Check if state is locked
   ```bash
   aws dynamodb scan --table-name terraform-locks --filter-expression "attribute_exists(LockID)"
   # What to look for: active lock entries with Info, Created timestamps
   ```

2. Check if lock owner is still alive
   ```bash
   # Match the lock info (runner ID, PID) to active processes
   # If no active Terraform process matches → orphaned lock
   ```

3. Check state file integrity
   ```bash
   terraform state pull > /tmp/state-check.json
   python -m json.tool /tmp/state-check.json > /dev/null
   # If JSON parse fails → corrupted state
   ```

## Investigation

1. **Orphaned lock (most common)**
   ```bash
   aws dynamodb get-item --table-name terraform-locks \
     --key '{"LockID": {"S": "<state-file-path-md5>"}}'
   # Check Created timestamp — if >30 min old, likely orphaned
   ```

2. **State corruption**
   ```bash
   terraform state pull | jq '.serial'
   # If fails to parse or serial is wrong → corrupted
   # Check S3 versioning for previous good version
   aws s3api list-object-versions --bucket <state-bucket> --prefix <state-key>
   ```

3. **State drift (plan shows unexpected changes)**
   ```bash
   terraform plan -no-color > /tmp/plan.txt
   grep -c "will be destroyed\|must be replaced" /tmp/plan.txt
   ```

4. **Decision point:**
   - IF orphaned lock → proceed to Mitigation Option A
   - IF state corrupted → proceed to Mitigation Option B
   - IF state drift → proceed to Mitigation Option C

## Mitigation

### Option A: Force-unlock orphaned state lock

```bash
# Verify no active Terraform process holds the lock
terraform force-unlock <lock-id>
# Re-run the blocked pipeline
```

### Option B: Restore state from S3 version history

```bash
# List available versions:
aws s3api list-object-versions --bucket <bucket> --prefix <key> --max-items 5
# Restore previous version:
aws s3api get-object --bucket <bucket> --key <key> --version-id <version-id> restored-state.json
terraform state push restored-state.json
```

### Option C: Fix state drift (import or taint)

```bash
# For resources that exist but aren't in state:
terraform import <resource-address> <resource-id>
# For resources that need recreation:
terraform taint <resource-address>
terraform apply
```

**After mitigation:** Run `terraform plan` — should show no changes (clean state).

## Verification

- [ ] `terraform plan` shows no unexpected changes
- [ ] No active locks in DynamoDB
- [ ] CI/CD pipeline succeeds on next run
- [ ] State serial number incremented correctly

```bash
terraform plan
# Expected: "No changes. Your infrastructure matches the configuration."
aws dynamodb scan --table-name terraform-locks --select COUNT
# Expected: Count: 0
```

## Failure Signals

- Plan still shows unexpected destroys after state restore
- Force-unlock fails (permission denied)
- State push rejected (serial number conflict)
- Resources actually missing from cloud (real drift)

**If any failure signal is present:** Escalate — do NOT apply without understanding drift.

## Rollback

1. **If wrong state version restored:** Re-pull correct version from S3
2. **If terraform apply created/destroyed wrong resources:** Immediate manual remediation
3. **If state completely lost:** Rebuild from `terraform import` for each resource

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| State corruption confirmed | Infrastructure Lead | #platform-support | 10 min |
| Unexpected resource deletion in plan | EM + Infra Lead | #incident-response | Immediate |
| Cannot unlock after 15 min | Platform team | #platform-support | 10 min |
| Need to rebuild state from scratch | Infra team (all hands) | #incident-response | 30 min |

## Notes

- **Always backup state before any state manipulation.** `terraform state pull > backup-$(date +%s).json`
- **S3 versioning is your lifeline.** Never disable it on state buckets.
- **force-unlock should only be used when you've confirmed no active process holds the lock.**
- **State drift during apply = potential data loss.** Never `terraform apply` without reviewing the plan carefully.
- See [[INC-025-terraform-state-lock-contention]] for real-world orphaned lock example.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Create a test lock in staging DynamoDB, execute force-unlock procedure.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Infrastructure Team | Initial publication |
