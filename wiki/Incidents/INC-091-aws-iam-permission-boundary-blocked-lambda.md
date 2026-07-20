---
id: INC-091
title: AWS IAM Permission Boundary Silently Blocked Lambda Execution Role
severity: SEV-2
service: payment-service
environment: prod
category: security
date: 2026-04-23
duration: "1h 10m"
tags:
  - incident
  - aws
  - iam
  - lambda
  - permission-boundary
  - payment-service
  - prod
---

## Summary

A security team IAM hardening change added a permission boundary to all Lambda execution roles, restricting actions to an approved list. A payment-service Lambda (invoice generation) that required `s3:GetObject` on a cross-account bucket was not in the boundary's allowed list. The Lambda began returning `AccessDenied` silently — no CloudWatch alarm existed — and invoice generation failed undetected for 70 minutes.

## Symptoms

- Users: "Invoice download button returning an error"
- Lambda CloudWatch logs: `AccessDeniedException: User is not authorized to perform s3:GetObject`
- payment-service invoice API: HTTP 500 with generic error message
- No alert: Lambda error rate metric had no alarm configured

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~480 users unable to download invoices |
| Services degraded | payment-service invoice endpoint |
| Revenue impact | N/A (invoices queued for retry) |
| Duration | 11:00 → 12:10 UTC (1h 10m) |
| Data loss | None |
| SLA breach | Yes — invoice availability SLA (4h) not breached but internal target missed |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 10:55 | IAM permission boundary applied to all Lambda roles |
| 11:00 | Invoice Lambda begins failing |
| 12:10 | User complaint ticket reached on-call |
| 12:15 | CloudWatch logs reviewed; AccessDenied identified |
| 12:30 | Permission boundary updated; Lambda recovered |

## Diagnosis

1. Checked Lambda logs in CloudWatch:
   ```bash
   aws logs filter-log-events --log-group-name /aws/lambda/invoice-generator \
     --filter-pattern "AccessDeniedException" --start-time $(date -d '2h ago' +%s000)
   # 480 AccessDeniedException events
   ```
2. Confirmed permission boundary:
   ```bash
   aws iam get-role --role-name invoice-lambda-exec | jq '.Role.PermissionsBoundary'
   # arn:aws:iam::123456789:policy/LambdaBoundary-v2
   ```
3. Checked boundary policy — `s3:GetObject` not present:
   ```bash
   aws iam get-policy-version --policy-arn arn:aws:iam::123456789:policy/LambdaBoundary-v2 \
     --version-id v2 | jq '.PolicyVersion.Document.Statement[].Action'
   # No s3 actions listed
   ```

## Resolution

1. Added `s3:GetObject` to the permission boundary for the invoice Lambda:
   ```bash
   aws iam create-policy-version --policy-arn arn:aws:iam::123456789:policy/LambdaBoundary-v2 \
     --policy-document file://boundary-v3.json --set-as-default
   ```
2. Lambda began succeeding immediately — no restart required
3. Queued failed invoice requests replayed successfully

## Post-Incident Review

**What went well:**
- Quick fix once identified — IAM policy update took 5 minutes

**What needs improvement:**
- No alarm on Lambda error rate
- Permission boundary change applied without testing against all affected Lambdas
- Silent `AccessDenied` not surfaced to user-facing error response meaningfully

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add CloudWatch alarm: Lambda error rate > 1% for any function | Observability | 2026-04-30 | Open |
| Test permission boundary changes against all Lambda roles in staging first | Security | 2026-04-30 | Open |
| Maintain inventory of all Lambda cross-account S3 access requirements | Security | 2026-05-07 | Open |

## Links

- Runbooks: [[RB-023-secrets-rotation-failure]]
- Related incidents: [[INC-037-s3-bucket-policy-deny-all]], [[INC-038-vault-seal-auto-unseal-failure]]
