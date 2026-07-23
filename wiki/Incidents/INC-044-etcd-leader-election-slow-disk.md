---
id: INC-044
title: etcd Leader Election Thrashing Due to Slow Disk I/O
severity: SEV-1
service: kubernetes-control-plane
environment: prod
category: outage
date: 2026-04-12
duration: "15m"
tags:
  - incident
  - etcd
  - kubernetes
  - disk
  - leader-election
  - critical
  - prod
error_family: unknown
resolution_runbook: RB-009
resolution_outcome: resolved
---

## Summary

At 04:30 UTC on 2026-04-12, the etcd cluster began leader election thrashing after a noisy neighbor EBS volume on the same physical host caused etcd fsync latency to spike from 2ms to 800ms. The etcd leader missed heartbeat deadlines, triggering repeated leader elections every 5-10 seconds. The Kubernetes API server became intermittently unavailable, causing kubectl timeouts and failed deployments cluster-wide.

## Symptoms

- PagerDuty: `Etcd-LeaderChangesHigh` at 04:32 UTC
- etcd metrics: `etcd_server_leader_changes_seen_total` climbing rapidly
- kube-apiserver: intermittent 504 Gateway Timeout
- kubectl commands: `error: the server was unable to return a response`
- All deployments and scaling operations stalled

## Diagnosis

1. Confirmed leader election thrashing
   ```bash
   kubectl exec etcd-0 -n kube-system -- etcdctl endpoint status --cluster -w table
   # Leader changing every 5-10 seconds
   ```

2. Checked etcd disk latency
   ```bash
   kubectl exec etcd-0 -n kube-system -- etcdctl check perf
   # FAIL: fsync latency 800ms (threshold: 10ms)
   ```

3. EBS CloudWatch metrics: `VolumeQueueLength` at 45, `VolumeThroughputPercentage` at 99%

4. Identified noisy neighbor via AWS support case (shared physical host)

## Resolution

1. **Mitigate:** Migrated etcd EBS volume to io2 with provisioned IOPS
   ```bash
   aws ec2 modify-volume --volume-id vol-abc123 --volume-type io2 --iops 10000
   ```

2. **Fix:** Restarted etcd pod to re-establish stable leadership
   ```bash
   kubectl delete pod etcd-0 -n kube-system
   ```

3. **Verify:** Leader stable, API server responsive
   ```bash
   kubectl exec etcd-0 -n kube-system -- etcdctl endpoint health
   # healthy: true, took: 2ms
   ```

## Post-Incident Review

- etcd on gp3 volumes is vulnerable to noisy neighbor IOPS contention
- Migrated all etcd volumes to io2 with provisioned IOPS (10,000)
- Added alert: `etcd_disk_wal_fsync_duration_seconds` P99 > 50ms
- Added dedicated host placement for etcd nodes

## Links

- Runbooks: [[RB-009-etcd-cluster-recovery]]
- Related incidents: [[INC-004-k8s-node-notready]]
