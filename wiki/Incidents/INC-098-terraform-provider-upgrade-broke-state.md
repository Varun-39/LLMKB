---
id: INC-098
title: Terraform Provider Upgrade Caused State Drift and Unexpected Resource Deletion
severity: SEV-1
service: general
environment: prod
category: data-loss
date: 2026-05-07
duration: "1h 55m"
tags:
  - incident
  - terraform
  - state
  - provider-upgrade
  - infrastructure
  - prod
---

## Summary

A Terraform AWS provider upgrade from 4.x to 5.x changed the internal resource ID format for security group rules. On the next `terraform apply`, Terraform interpreted existing rules as deleted (old ID format) and planned new ones (new format), resulting in 18 security group rules being removed and re-added during a 90-second window where production services were briefly exposed without firewall rules.

## Symptoms

- Terraform plan output: `18 resources to destroy, 18 resources to add`
- Unexpected `terraform apply` succeeded (engineer assumed it was a re-create, not a gap)
- VPC flow logs: 90-second window with no deny rules on internal SGs
- Security alert: unexpected inbound connections during the window
- No application impact observed (connections were benign)

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | None directly |
| Services degraded | Security posture temporarily degraded |
| Revenue impact | N/A |
| Duration | 14:00 → 15:55 UTC (investigation + re-audit) |
| Data loss | None |
| SLA breach | Potential security compliance SLA concern |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 13:55 | Terraform provider upgraded to AWS 5.x in CI |
| 14:00 | `terraform apply` run against prod |
| 14:00 | 18 SG rules destroyed and recreated (90-second gap) |
| 14:02 | SecOps alert: unexpected flow log entries |
| 14:10 | SecOps contacts SRE |
| 14:30 | Terraform state change identified as cause |
| 15:55 | Full audit of SG rules completed; state confirmed clean |

## Diagnosis

1. Checked Terraform plan that was applied:
   ```bash
   terraform show tfplan-20260507-1400.txt | grep -c "will be destroyed"
   # 18
   ```
2. Confirmed provider upgrade caused ID format change:
   ```bash
   # Old format: sgr-xxxxxxxx
   # New format: sgrule-xxxxxxxxxxxxxxxx  (AWS 5.x changed attribute handling)
   ```
3. Verified actual AWS state never had a gap vs expected config — only state file drift:
   ```bash
   aws ec2 describe-security-groups --group-ids sg-xxxx | jq '.SecurityGroups[0].IpPermissions | length'
   # 18  — rules always present in AWS, gap was only in state tracking
   ```

## Resolution

1. **Verified all security group rules present in AWS** (no actual loss)
2. **State imported** to reconcile Terraform state with reality:
   ```bash
   terraform import aws_vpc_security_group_ingress_rule.rule_N sgr-xxxxxxxx
   ```
3. Full SG audit completed with security team sign-off
4. **Fix:** Added provider version pinning and migration testing gate in CI:
   ```hcl
   required_providers {
     aws = { version = "~> 5.0" }
   }
   ```

## Post-Incident Review

**What went well:**
- SecOps alert fired within 2 minutes of the SG gap

**What needs improvement:**
- Provider upgrades applied to prod without a state migration dry-run
- `terraform apply` allowed to proceed without human review of destroy operations

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Block `terraform apply` if plan contains > 0 `destroy` operations without explicit approval | Platform | 2026-05-14 | Open |
| Add provider upgrade to change management process with mandatory staging test | Platform | 2026-05-14 | Open |
| Pin all Terraform provider versions with `~>` constraints | Platform | 2026-05-14 | Open |

## Links

- Runbooks: [[RB-016-terraform-state-recovery]]
- Related incidents: [[INC-025-terraform-state-lock-contention]]
