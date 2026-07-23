---
id: INC-069
title: Kubelet Image GC Evicting Running Pods Due to Disk Pressure
severity: SEV-2
service: kubernetes-nodes
environment: prod
category: degradation
date: 2026-06-15
duration: "20m"
tags:
  - incident
  - kubernetes
  - kubelet
  - garbage-collection
  - disk
  - eviction
  - high
  - prod
error_family: node-disk-pressure
resolution_runbook: RB-003
resolution_outcome: resolved
---

## Summary

Worker-node-12 accumulated 180 unused container images (45GB) from CI/CD test runs. When regular application logs pushed disk usage above 85%, kubelet triggered image garbage collection followed by pod eviction. 6 production pods were evicted from the node, causing service degradation as they rescheduled.

## Symptoms

- 6 pods on node-12 suddenly terminated (Evicted status)
- Node condition: `DiskPressure: True`
- kubectl events: `The node was low on resource: ephemeral-storage`
- Services with single-replica deployments experienced brief outage

## Diagnosis

1. Confirmed eviction
   ```bash
   kubectl get pods --all-namespaces --field-selector spec.nodeName=worker-node-12,status.phase=Failed | grep Evicted
   # 6 evicted pods
   ```

2. Disk pressure from unused images
   ```bash
   ssh ec2-user@worker-node-12
   docker image ls | wc -l
   # 180 images, 45GB total
   df -h /var/lib/docker
   # 88% used
   ```

3. kubelet GC thresholds: `imageGCHighThresholdPercent: 85`, `evictionHard: nodefs.available < 10%`

## Resolution

1. **Mitigate:** Manually pruned unused images
   ```bash
   docker image prune -a -f --filter "until=48h"
   # Freed 38GB
   ```

2. **Fix:** Added weekly image prune CronJob to all nodes

3. **Verify:** Node DiskPressure cleared, evicted pods rescheduled

## Post-Incident Review

- CI/CD images accumulated without cleanup
- Added node-level image prune DaemonSet (runs daily, removes images >24h unused)
- Lowered imageGCHighThresholdPercent to 70% (earlier cleanup)
- Set min 2 replicas for all production deployments (survive single-node eviction)

## Links

- Runbooks: [[RB-003-disk-space-full]]
- Related incidents: [[INC-014-k8s-node-disk-pressure]]
