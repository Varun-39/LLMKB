---
id: INC-061
title: DynamoDB Hot Partition Throttling — User Profile Reads Failed
severity: SEV-2
service: user-service
environment: prod
category: degradation
date: 2026-06-01
duration: "30m"
tags:
  - incident
  - dynamodb
  - aws
  - throttling
  - hot-partition
  - high
  - prod
error_family: unknown
resolution_runbook: RB-013
resolution_outcome: resolved
---

## Summary

A viral marketing campaign drove 80% of all user-profile reads to a single DynamoDB partition (celebrity user profile viewed 50K times/sec). The partition hit its throughput limit (3,000 RCU/partition), causing `ProvisionedThroughputExceededException` for all reads landing on that partition — including reads for other users hashed to the same partition. User profile pages returned errors for ~15,000 users for 30 minutes.

## Symptoms

- CloudWatch: `ReadThrottleEvents` spike on `user-profiles` table
- user-service logs: `ProvisionedThroughputExceededException` at 2,000/min
- Celebrity profile page: 100% error rate
- Other users on same partition: intermittent 500 errors
- Table-level RCU utilization: only 40% (throttling was partition-level)

## Diagnosis

1. Confirmed throttling
   ```bash
   aws cloudwatch get-metric-statistics --namespace AWS/DynamoDB \
     --metric-name ReadThrottleEvents --dimensions Name=TableName,Value=user-profiles \
     --period 60 --statistics Sum
   # 120,000 throttle events in last 5 min
   ```

2. Identified hot key
   ```bash
   # CloudWatch Contributor Insights: partition key "user:celebrity123" = 80% of reads
   ```

3. Table capacity: 50,000 RCU provisioned (sufficient overall, but single partition limited to 3,000)

## Resolution

1. **Mitigate:** Added DAX (DynamoDB Accelerator) cache in front of reads
   ```bash
   # DAX cluster already provisioned for staging; promoted to prod
   aws dax create-cluster --cluster-name user-profiles-cache --node-type dax.r5.large --replication-factor 3
   ```

2. **Fix short-term:** Added application-level cache for hot user profiles (TTL 30s)

3. **Verify:** Throttle events dropped to 0 within 5 minutes of cache activation

## Post-Incident Review

- Single hot key can throttle an entire DynamoDB partition
- Deployed DAX for all user-profile reads (eliminates hot partition issue)
- Added cache-aside pattern: popular profiles cached in Redis with 30s TTL
- Added alert: throttle events >0 for any DynamoDB table

## Links

- Runbooks: [[RB-013-redis-memory-management]]
- Related incidents: [[INC-039-redis-maxmemory-eviction-storm]]
