---
id: INC-065
title: kube-proxy iptables Rule Explosion — 90-Second Service Resolution Delay
severity: SEV-2
service: kubernetes-networking
environment: prod
category: degradation
date: 2026-06-08
duration: "50m"
tags:
  - incident
  - kubernetes
  - kube-proxy
  - iptables
  - networking
  - latency
  - high
  - prod
error_family: unknown
resolution_runbook: RB-007
resolution_outcome: resolved
---

## Summary

After reaching 12,000 Kubernetes Services in the cluster (primarily from a misconfigured CronJob creating Service resources per-run), kube-proxy's iptables sync took 90 seconds per cycle. During each sync, packet forwarding was briefly interrupted, causing intermittent 1-3 second latency spikes on all intra-cluster communication. The issue built up gradually over 2 weeks.

## Symptoms

- Intermittent latency spikes (1-3s) on all service-to-service calls
- kube-proxy CPU: 80% (iptables rule compilation)
- `iptables -L | wc -l`: 480,000 rules
- Service count: 12,000 (expected: ~200)

## Diagnosis

1. Checked service count
   ```bash
   kubectl get svc --all-namespaces | wc -l
   # 12,047
   ```

2. Found culprit: CronJob creating orphaned Services
   ```bash
   kubectl get svc -n batch --sort-by='.metadata.creationTimestamp' | tail -20
   # batch-export-run-20260601, batch-export-run-20260602, ... (11,800 services)
   ```

3. kube-proxy sync duration
   ```bash
   kubectl logs -l k8s-app=kube-proxy -n kube-system --tail=20 | grep "sync.*rules"
   # "SyncProxyRules took 92.4s to sync 480,000 iptables rules"
   ```

## Resolution

1. **Mitigate:** Deleted orphaned batch Services
   ```bash
   kubectl get svc -n batch -o name | xargs -P10 kubectl delete -n batch
   # Deleted 11,800 services
   ```

2. **Fix:** Fixed CronJob to not create Service resources; switched kube-proxy to IPVS mode

3. **Verify:** iptables rule count dropped to 1,200, sync time <1s

## Post-Incident Review

- iptables mode does not scale beyond ~5,000 Services
- Migrated kube-proxy to IPVS mode (O(1) lookup vs O(n) iptables)
- Added alert: if Service count >500, investigate
- Fixed CronJob to clean up resources after completion

## Links

- Runbooks: [[RB-007-pod-crash-investigation]]
- Related incidents: [[INC-013-k8s-pending-pods-resource-pressure]]
