---
id: INC-035
title: MongoDB Election Timeout During Network Partition
severity: SEV-1
service: product-catalog
environment: prod
category: outage
date: 2026-04-09
duration: "12m"
tags:
  - incident
  - mongodb
  - replication
  - election
  - network-partition
  - database
  - critical
---

## Summary

A network partition between availability zones isolated the MongoDB primary from both secondaries for 45 seconds. This triggered a new election, but the two secondaries couldn't agree on a new primary (both at the same oplog position). The replica set was without a primary for 12 minutes, causing all writes to product-catalog to fail.

## Symptoms

- Application errors: `MongoServerError: not primary and secondaryOk=false`
- MongoDB logs: `transition to RECOVERING`, `stepping down`
- `rs.status()` showed: no PRIMARY member, two SECONDARY, one (old primary) RECOVERING
- 12 minutes of write failures on product catalog
- Read-preference `primary` queries also failing

## Diagnosis

1. Checked replica set status:
   ```javascript
   rs.status().members.forEach(m => print(m.name, m.stateStr))
   // mongo-01: RECOVERING, mongo-02: SECONDARY, mongo-03: SECONDARY
   ```
2. Election log showed repeated failed votes:
   ```
   VoteRequester: not getting vote from mongo-02 because it has already voted
   ```
3. Both secondaries had identical `lastAppliedOpTime` — neither had priority over the other
4. `electionTimeoutMillis: 10000` (default) — re-elections attempted every 10s but kept deadlocking
5. Network partition lasted 45s but the deadlock persisted for 12 minutes after connectivity restored

## Resolution

1. Forced a stepdown and immediate election from the most up-to-date node:
   ```javascript
   // On mongo-02:
   rs.stepDown(120, 60) // Force re-election
   ```
2. mongo-03 won the election and became primary
3. Verified replication caught up:
   ```javascript
   rs.printReplicationInfo()
   // oplog: 0 seconds behind primary
   ```
4. Set priority to break ties in future:
   ```javascript
   cfg = rs.conf()
   cfg.members[0].priority = 3  // preferred primary
   cfg.members[1].priority = 2
   cfg.members[2].priority = 1
   rs.reconfig(cfg)
   ```

## Post-Incident Review

- Equal-priority members can deadlock elections when partition heals
- Set distinct priorities to ensure deterministic election winner
- Reduced `electionTimeoutMillis` to 5000 for faster recovery
- Added monitoring: alert if replica set has no primary for > 30 seconds
- Application read-preference updated to `primaryPreferred` for read resilience

## Links

- Related: [[RB-019-kubernetes-node-notready]]
