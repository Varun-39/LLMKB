---
id: INC-055
title: EFS Throughput Throttled — Shared Storage I/O Starvation
severity: SEV-2
service: media-processing
environment: prod
category: degradation
date: 2026-05-16
duration: "40m"
tags:
  - incident
  - aws
  - efs
  - storage
  - throughput
  - throttle
  - high
  - prod
---

## Summary

The shared EFS filesystem used by the media-processing pipeline was throttled to burst credit exhaustion. A batch video transcoding job consumed all available burst throughput (100 MiB/s), leaving other consumers (thumbnail generation, file uploads) starved for I/O. File operations that normally complete in 200ms took 15-30 seconds, causing timeouts across all media services.

## Symptoms

- CloudWatch: `BurstCreditBalance` dropped to 0 for EFS filesystem
- media-processing latency: 200ms → 28s
- File upload timeouts from user-facing endpoints
- CloudWatch: `PercentIOLimit` at 100%

## Diagnosis

1. Confirmed EFS throttling
   ```bash
   aws efs describe-file-systems --file-system-id fs-abc123
   # ThroughputMode: bursting, BurstCreditBalance: 0
   aws cloudwatch get-metric-statistics --namespace AWS/EFS --metric-name PercentIOLimit \
     --dimensions Name=FileSystemId,Value=fs-abc123 --period 300 --statistics Average
   # 100% for last 30 minutes
   ```

2. Identified batch job consuming all throughput
   ```bash
   # NFS stats from media-processing pods showed 95% of I/O from transcoding job
   ```

## Resolution

1. **Mitigate:** Switched EFS to provisioned throughput mode (256 MiB/s)
   ```bash
   aws efs update-file-system --file-system-id fs-abc123 \
     --throughput-mode provisioned --provisioned-throughput-in-mibps 256
   ```

2. **Fix:** Moved video transcoding to a separate EFS filesystem with its own throughput budget

3. **Verify:** I/O latency returned to baseline, burst credits recovering

## Post-Incident Review

- Shared EFS between latency-sensitive and batch workloads is a recipe for throttling
- Separated batch and interactive workloads onto different filesystems
- Added CloudWatch alarm: BurstCreditBalance < 1TB (6-hour warning before exhaustion)
- Configured provisioned throughput for production media filesystem

## Links

- Runbooks: [[RB-003-disk-space-full]]
- Related incidents: [[INC-031-nfs-stale-handle-pod-io]]
