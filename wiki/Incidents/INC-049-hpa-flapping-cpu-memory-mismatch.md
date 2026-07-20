---
id: INC-049
title: HPA Flapping — Scale Up/Down Oscillation Causing Request Drops
severity: SEV-2
service: search-api
environment: prod
category: degradation
date: 2026-05-02
duration: "45m"
tags:
  - incident
  - kubernetes
  - hpa
  - autoscaling
  - flapping
  - high
  - prod
---

## Summary

The Horizontal Pod Autoscaler for search-api oscillated between 3 and 12 replicas every 2 minutes for 45 minutes. Each scale-down removed pods that were still receiving traffic, causing request drops. Root cause: HPA was configured with a CPU target of 50%, but the search workload was memory-bound. CPU usage fluctuated wildly as queries arrived in bursts, triggering rapid scaling decisions.

## Symptoms

- Intermittent 503 errors on search endpoints (every 2 min)
- HPA events: `SuccessfulRescale` alternating between 3 and 12 replicas
- Pod terminations every 2 minutes
- Search latency P99 oscillating between 200ms and 3s

## Diagnosis

1. Observed HPA oscillation
   ```bash
   kubectl get hpa search-api -n search -w
   # REPLICAS bouncing: 12 → 3 → 12 → 3 (every 90-120s)
   ```

2. CPU usage averaging 20% at idle, spiking to 80% during query bursts
   ```bash
   kubectl top pods -n search -l app=search-api
   # Wildly varying: 15m to 950m between pods
   ```

3. HPA stabilization window was at default (0s for scale-down)

## Resolution

1. **Mitigate:** Set HPA to fixed replica count temporarily
   ```bash
   kubectl scale deployment/search-api -n search --replicas=8
   kubectl patch hpa search-api -n search -p '{"spec":{"minReplicas":8,"maxReplicas":8}}'
   ```

2. **Fix:** Changed HPA metric to custom metric (requests per second) and added stabilization window
   ```bash
   # Added: behavior.scaleDown.stabilizationWindowSeconds: 300
   # Changed target: custom metric "http_requests_per_second" target 100
   ```

3. **Verify:** Stable replica count, no more oscillation

## Post-Incident Review

- CPU is a poor autoscaling metric for search workloads (bursty, memory-bound)
- Added 5-minute stabilization window for scale-down
- Switched to custom metric (RPS) for search-api HPA
- Added alert: if HPA replica count changes >3 times in 10 minutes

## Links

- Runbooks: [[RB-004-high-cpu-usage]]
- Related incidents: [[INC-013-k8s-pending-pods-resource-pressure]]
