---
id: INC-025
title: Terraform State Lock Contention Blocking Infrastructure Changes
severity: SEV-3
service: infrastructure
environment: prod
category: configuration
date: 2026-02-11
duration: "2h10m"
tags:
  - incident
  - terraform
  - state
  - ci-cd
  - infrastructure
  - lock
error_family: terraform-state-lock
resolution_runbook: RB-016
resolution_outcome: resolved
---

## Summary

All Terraform `plan` and `apply` operations across 4 CI/CD pipelines failed with state lock errors for over 2 hours. Root cause: a GitHub Actions runner was terminated mid-`apply` (spot instance reclaim), leaving the DynamoDB state lock unreleased. All subsequent infrastructure changes were blocked.

## Symptoms

- All Terraform pipelines failing with: `Error: Error acquiring the state lock`
- Lock info showed: `ID: a3f2b1c9-..., Created: 2026-02-11T06:42:12Z, Info: Operation: OperationTypeApply`
- GitHub Actions: 4 workflows queued and failing
- Engineers unable to deploy infrastructure changes
- No active Terraform process matching the lock ID

## Diagnosis

1. Identified the orphaned lock:
   ```bash
   aws dynamodb get-item --table-name terraform-locks --key '{"LockID": {"S": "s3://infra-state/prod/terraform.tfstate-md5"}}'
   ```
2. Lock was 2+ hours old with no active process
3. Checked GitHub Actions run history — the runner holding the lock was a spot instance that was reclaimed at 06:43 UTC (1 minute after acquiring the lock)
4. No automated lock timeout existed

## Resolution

1. Confirmed no active Terraform process was running for this state:
   ```bash
   # Checked all runners, no terraform process active
   ```
2. Force-unlocked the state:
   ```bash
   terraform force-unlock a3f2b1c9-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```
3. Re-ran the interrupted pipeline to ensure state consistency
4. Verified `terraform plan` showed no drift

## Post-Incident Review

- Spot instance reclaims during `apply` leave orphaned locks
- Moved critical infrastructure pipelines to on-demand runners
- Added a cron job that checks for locks older than 30 minutes and alerts
- Documented `force-unlock` procedure in runbook

## Links

- Related: [[RB-016-terraform-state-recovery]]
