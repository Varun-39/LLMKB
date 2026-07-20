---
id: INC-086
title: ConfigMap Hot-Reload Race Condition Crashed Payment Pods
severity: SEV-1
service: payment-service
environment: prod
category: outage
date: 2026-04-13
duration: "12m"
tags:
  - incident
  - kubernetes
  - configmap
  - hot-reload
  - race-condition
  - payment-service
  - prod
---

## Summary

payment-service uses inotify to hot-reload configuration from a mounted ConfigMap. A ConfigMap update (new rate limit values) caused a brief moment where the file was partially written (Kubernetes atomic symlink swap). The application read a truncated YAML file during the swap, failed to parse it, panicked, and all 4 payment-service pods crashed simultaneously — a full payment outage for 12 minutes.

## Symptoms

- All 4 payment-service pods entered `Error`/`CrashLoopBackOff` within 30 seconds
- payment-service logs: `panic: yaml: unexpected EOF` at config reload handler
- PagerDuty: `payment-service all pods down` SEV-1 fired
- api-gateway: payment endpoint returning 503

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All active payment sessions (~1,200) |
| Services degraded | payment-service (full outage) |
| Revenue impact | ~$18K in failed transactions |
| Duration | 15:05 → 15:17 UTC (12 min) |
| Data loss | None |
| SLA breach | Yes — payment availability SLA breached |
| Customer comms | Status page updated at 15:07 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 15:05 | ConfigMap updated via `kubectl apply` |
| 15:05 | Kubernetes begins propagating ConfigMap to mounted volumes |
| 15:05 | inotify fires; all pods read config simultaneously |
| 15:05 | Truncated YAML causes panic; all pods crash |
| 15:06 | SEV-1 alert fired |
| 15:08 | On-call acknowledged |
| 15:10 | Pods restarted manually with last-known-good config |
| 15:17 | Service fully recovered |

## Diagnosis

1. Confirmed all pods crashed at same timestamp:
   ```bash
   kubectl get pods -n payments -o wide
   # All 4 pods: CrashLoopBackOff, age 3m
   ```
2. Identified panic in logs:
   ```bash
   kubectl logs -n payments payment-service-xxx --previous
   # panic: yaml: unexpected EOF
   # goroutine 1 [running]: config.Reload(...)
   ```
3. Confirmed ConfigMap was recently updated:
   ```bash
   kubectl get configmap payment-config -n payments -o yaml | grep -A5 "annotations"
   # kubectl.kubernetes.io/last-applied-configuration: ...15:05 UTC
   ```

## Resolution

1. **Mitigate:** Reverted ConfigMap to last-known-good values:
   ```bash
   kubectl apply -f config/payment-config-stable.yaml -n payments
   ```
2. **Restarted pods:**
   ```bash
   kubectl rollout restart deployment/payment-service -n payments
   ```
3. **Fix (deployed next day):** Added YAML validation + fallback to cached config on parse failure before applying hot-reload
4. **Verify:**
   ```bash
   kubectl get pods -n payments
   # All 4 Running, READY 1/1
   ```

## Post-Incident Review

**What went well:**
- SEV-1 alert fired in under 60 seconds

**What needs improvement:**
- No validation of config file before applying hot-reload
- All pods reloaded simultaneously — no staggered reload
- No fallback to last-valid config on parse error

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add YAML validation before applying config reload | Backend | 2026-04-20 | Open |
| Implement staggered hot-reload (reload one pod at a time) | Backend | 2026-04-20 | Open |
| Cache last-valid config; fall back on parse failure | Backend | 2026-04-20 | Open |

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]]
- Related incidents: [[INC-019-broken-feature-flag-auth]], [[INC-020-bad-config-rollout-payment]]
