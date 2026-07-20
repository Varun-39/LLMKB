---
id: INC-026
title: Redis Cluster Slot Migration Failure
severity: SEV-2
service: session-cache
environment: prod
category: degradation
date: 2026-02-18
duration: "45m"
tags:
  - incident
  - redis
  - cluster
  - slot-migration
  - cache
  - prod
---

## Summary

A Redis cluster rebalance (triggered by adding a new node) left 1,024 hash slots in `migrating/importing` state. Keys in those slots returned `MOVED` or `ASK` redirects that client libraries failed to handle cleanly. Session lookups for ~15% of users returned errors for 45 minutes.

## Symptoms

- Application logs: `redis.exceptions.ResponseError: CLUSTERDOWN The cluster is down` (intermittent)
- `MOVED 5462 10.0.3.7:6379` responses in client debug logs
- Session cache hit rate dropped from 94% to 79%
- User-facing: "Session expired, please log in again" errors for subset of users
- `redis-cli cluster info` showed `cluster_state:ok` but `cluster_slots_migrating:1024`

## Diagnosis

1. Checked cluster slot status:
   ```bash
   redis-cli -c -h redis-cluster-01 cluster nodes
   # Node redis-04 showed [5461-6484->-importing] status
   # Node redis-02 showed [5461-6484-<-migrating] status
   ```
2. The migration was initiated 50 minutes ago and stalled
3. Root cause: redis-02 experienced a brief network partition during slot migration, causing the migration to hang mid-transfer
4. Client library (`ioredis`) was not configured to follow `ASK` redirects automatically

## Resolution

1. Fixed the stalled migration by completing it manually:
   ```bash
   redis-cli -c -h redis-04 cluster setslot 5461 importing <redis-02-node-id>
   # For each stuck slot:
   redis-cli -c -h redis-04 cluster setslot <slot> node <redis-04-node-id>
   redis-cli -c -h redis-02 cluster setslot <slot> node <redis-04-node-id>
   ```
2. Verified all slots assigned and stable:
   ```bash
   redis-cli -c cluster info | grep cluster_slots
   # cluster_slots_assigned:16384, cluster_slots_ok:16384
   ```
3. Updated client config to enable `ASK` redirect handling
4. Confirmed session hit rate recovered to 94%

## Post-Incident Review

- Slot migrations should not be run during peak hours
- Added maintenance window requirement for cluster rebalancing
- Client libraries must be configured to handle `MOVED` and `ASK` redirects
- Alert added: `cluster_slots_migrating > 0` for more than 5 minutes

## Links

- Related: [[RB-013-redis-memory-management]]
