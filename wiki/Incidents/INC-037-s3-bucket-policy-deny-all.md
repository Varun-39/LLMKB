---
id: INC-037
title: S3 Bucket Policy Accidentally Denied All Access
severity: SEV-1
service: media-service
environment: prod
category: configuration
date: 2026-03-05
duration: "35m"
detection_gap: "4m"
tags:
  - incident
  - s3
  - aws
  - iam
  - configuration
  - critical
  - prod
  - media
error_family: unknown
resolution_runbook: RB-016
resolution_outcome: resolved
---

## Summary

At 10:22 UTC on 2026-03-05, an infrastructure engineer applied a Terraform change to the `prod-media-assets` S3 bucket policy that inadvertently included an explicit `Deny *` statement for all principals. All reads and writes to the media bucket failed immediately, breaking image uploads, CDN origin fetches, and media processing pipelines for 35 minutes.

## Symptoms

- CloudWatch alarm: `S3-403ErrorRateHigh` at 10:26 UTC
- media-service logs: `AccessDenied: Access Denied` on all PutObject and GetObject calls
- CDN: 403 errors on all media asset URLs, cache misses returning errors
- User reports: profile images, product thumbnails, and file uploads all broken
- Terraform apply output (from CI): `aws_s3_bucket_policy.media: Modification complete`

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~15,000 active users (all image/media functionality broken) |
| Services degraded | media-service, CDN origin, image-processing-worker |
| Revenue impact | ~$12K in failed uploads and broken product pages |
| Duration | 10:22 → 10:57 UTC (35 min) |
| Data loss | None — uploads failed cleanly, no data corrupted |
| SLA breach | Yes — media availability SLA (99.9%) breached |
| Customer comms | Status page updated at 10:30 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 10:20 | Terraform apply started for bucket policy update (adding CORS headers) |
| 10:22 | Policy applied with `Deny *` statement active |
| 10:26 | Alert fired: `S3-403ErrorRateHigh` |
| 10:27 | On-call acknowledged (Jordan Liu) |
| 10:35 | Bucket policy identified as cause via CloudTrail |
| 10:42 | Previous bucket policy restored via AWS CLI |
| 10:45 | Media operations resumed |
| 10:57 | CDN caches cleared, all assets serving, incident closed |

## Diagnosis

1. Confirmed 403 errors on S3 operations
   ```bash
   aws s3 ls s3://prod-media-assets/ --region us-east-1
   # An error occurred (AccessDenied) when calling the ListObjectsV2 operation
   ```

2. Checked bucket policy
   ```bash
   aws s3api get-bucket-policy --bucket prod-media-assets | jq '.Policy | fromjson'
   # Found: {"Effect": "Deny", "Principal": "*", "Action": "s3:*", "Resource": "arn:aws:s3:::prod-media-assets/*"}
   ```

3. CloudTrail showed the PutBucketPolicy event at 10:22 from the CI/CD role

4. Reviewed Terraform diff — a merge conflict left a `Deny` block from a security hardening branch that was meant for a different bucket

## Resolution

1. **Mitigate:** Restored the previous bucket policy from version history
   ```bash
   aws s3api put-bucket-policy --bucket prod-media-assets --policy file://previous-policy.json
   ```

2. **Fix:** Reverted the Terraform commit and re-applied
   ```bash
   git revert abc123f
   terraform apply -target=aws_s3_bucket_policy.media
   ```

3. **Verify:** Confirmed reads and writes working
   ```bash
   aws s3 cp test.txt s3://prod-media-assets/test.txt
   aws s3 ls s3://prod-media-assets/test.txt
   # Upload and list successful
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| S3 access denied on prod bucket | Page on-call + infra team | PagerDuty |
| CDN serving errors >5 min | Escalate to EM | #incident-response |
| Cannot restore policy (IAM lockout) | Engage AWS support | #platform-support |

## Post-Incident Review

**What went well:**
- CloudTrail audit trail made it trivial to identify the change and author
- S3 bucket versioning allowed quick policy restore

**What needs improvement:**
- No `terraform plan` review gate for IAM/policy changes in CI
- Merge conflict resolution introduced the Deny block — no automated policy validation
- No pre-apply check that verifies bucket is still accessible after policy change

**Contributing factors (beyond root cause):**
- Security hardening branch merged with conflicts, `Deny *` block from a different bucket copied in
- CI pipeline auto-applies on merge to main without policy simulation
- No integration test that validates S3 access post-Terraform apply

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Restore bucket policy, verify access | Jordan Liu | 2026-03-05 | Done |
| Add `aws s3api simulate-principal-policy` check to CI before apply | Infra team | 2026-03-19 | Open |
| Require manual approval for IAM/policy Terraform changes | Platform team | 2026-03-19 | Open |
| Add integration test: upload + read after infra apply | SRE team | 2026-03-26 | Open |

## Links

- Runbooks: [[RB-016-terraform-state-recovery]]
- Related incidents: [[INC-025-terraform-state-lock-contention]]
- PR/commit: revert commit `def456a`
- Post-mortem doc: N/A
