---
id: INC-072
title: OpenSearch Snapshot Failure — S3 Bucket Read-Only Policy
severity: SEV-3
service: opensearch
environment: prod
category: configuration
date: 2026-06-20
duration: "3h"
tags:
  - incident
  - opensearch
  - elasticsearch
  - snapshot
  - backup
  - s3
  - moderate
  - prod
error_family: unknown
resolution_runbook: RB-015
resolution_outcome: resolved
---

## Summary

OpenSearch automated snapshots silently failed for 14 days after an S3 bucket policy change removed write permissions for the OpenSearch service role. The issue was only discovered when a developer attempted to restore from snapshot for a data recovery exercise and found the latest successful snapshot was 14 days old.

## Symptoms

- No alerts (snapshot failures were not monitored)
- OpenSearch snapshot API: `repository_exception: [s3_backup] Could not write to repository`
- S3 bucket policy: missing `s3:PutObject` permission for OpenSearch role
- Latest successful snapshot: 14 days old
- RPO violated: should be 1 day, actual recovery point is 14 days

## Diagnosis

1. Checked snapshot status
   ```bash
   curl -s http://opensearch:9200/_snapshot/s3_backup/_all | jq '.snapshots[-1]'
   # state: "FAILED", reason: "repository_exception: Could not write to repository"
   # Last SUCCESS: 14 days ago
   ```

2. S3 bucket policy audit
   ```bash
   aws s3api get-bucket-policy --bucket opensearch-snapshots-prod | jq '.Policy | fromjson'
   # Missing: s3:PutObject for opensearch role (removed in security hardening 14 days ago)
   ```

## Resolution

1. **Fix:** Restored S3 write permission for OpenSearch role
   ```bash
   aws s3api put-bucket-policy --bucket opensearch-snapshots-prod --policy file://corrected-policy.json
   ```

2. **Verify:** Triggered manual snapshot, confirmed success
   ```bash
   curl -X PUT http://opensearch:9200/_snapshot/s3_backup/manual_recovery_$(date +%Y%m%d)
   # acknowledged: true
   ```

## Post-Incident Review

- Snapshot failures went undetected for 14 days (no monitoring)
- Added alert: if no successful snapshot in 25 hours
- Added snapshot status to daily SRE health check dashboard
- IAM policy changes now require backup team review for storage buckets

## Links

- Runbooks: [[RB-015-observability-pipeline-recovery]]
- Related incidents: [[INC-036-elasticsearch-red-unassigned-shards]]
