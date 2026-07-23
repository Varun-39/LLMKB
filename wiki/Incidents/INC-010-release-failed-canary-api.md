---
id: INC-010
title: Canary Release Failure — api-gateway v4.1.0 Error Spike
severity: SEV-2
service: api-gateway
environment: prod
category: deployment-failure
date: 2026-04-18
duration: "19m"
detection_gap: "3m"
tags:
  - incident
  - deployment
  - canary
  - api
  - high
  - prod
  - api-gateway
error_family: unknown
resolution_runbook: RB-006
resolution_outcome: resolved
---

## Summary

During a canary rollout of api-gateway v4.1.0 at 13:00 UTC on 2026-04-18, the canary pods immediately began producing HTTP 500 errors at an 18% rate due to an incompatible change in the upstream routing configuration format. The deployment pipeline's automated canary analysis detected the error rate spike within 3 minutes and paused the rollout. The on-call engineer confirmed and manually rolled back within 19 minutes of canary start, with blast radius limited to the 10% of traffic routed to the canary.

## Symptoms

- Deployment pipeline alert: `CanaryAnalysis-ErrorRateExceeded` at 13:03 UTC
- Canary pods: HTTP 500 rate 18% on all routes (baseline stable pods: 0.1%)
- api-gateway error logs: `NullPointerException: routeConfig.getUpstreams() returned null`
- Grafana canary dashboard: success rate dropped to 82% within 2 min of canary activation
- Stable pod traffic unaffected — error contained to 10% canary traffic slice

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~10% of active users (~1,400) routed to canary pods |
| Services degraded | api-gateway (canary pods only) |
| Revenue impact | ~$3K in failed requests during 19-min canary window |
| Duration | 13:00 → 13:19 UTC (19 min) |
| Data loss | None |
| SLA breach | No — only 10% of traffic affected, within SLA threshold |
| Customer comms | N/A — limited blast radius |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 13:00 | Canary rollout started for api-gateway v4.1.0 (10% traffic) |
| 13:01 | First HTTP 500 errors from canary pods |
| 13:03 | Automated canary analysis alert fired |
| 13:05 | On-call acknowledged (Marcus Webb) |
| 13:08 | ConfigMap schema mismatch identified as root cause |
| 13:12 | Canary rollout aborted via Argo Rollouts |
| 13:14 | Canary pods scaled to 0 |
| 13:19 | All traffic on stable v4.0.9, incident closed |

## Diagnosis

1. Confirmed error spike on canary pods only
   ```bash
   kubectl get pods -n gateway -l app=api-gateway
   # 3 stable pods: v4.0.9 — 0 errors
   # 1 canary pod: v4.1.0 — high restart rate
   kubectl logs api-gateway-canary-6d7f-rp99 -n gateway --tail=50
   # NullPointerException at RouteConfigLoader.java:87
   ```

2. Compared ConfigMap between stable and canary deployments
   ```bash
   kubectl get configmap api-gateway-config -n gateway -o yaml > stable-config.yaml
   kubectl get configmap api-gateway-canary-config -n gateway -o yaml > canary-config.yaml
   diff stable-config.yaml canary-config.yaml
   # canary-config missing 'upstreams' key under each route block
   ```

3. Confirmed config schema mismatch — v4.1.0 expects `routes[].upstreams[]`, ConfigMap still uses old `routes[].targets[]` key

## Resolution

1. **Mitigate:** Halted canary rollout immediately via deployment pipeline
   ```bash
   kubectl argo rollouts abort api-gateway-rollout -n gateway
   ```

2. **Fix:** Scaled canary pods to 0
   ```bash
   kubectl scale deployment/api-gateway-canary -n gateway --replicas=0
   ```

3. **Verify:** All traffic back on stable v4.0.9 pods
   ```bash
   kubectl get pods -n gateway -l app=api-gateway
   # 3 stable pods Running, canary scaled to 0
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Canary error rate >5% | Halt canary immediately | Automated pipeline + PagerDuty |
| Error spills to stable pods | Declare SEV-1, page EM + IC | #incident-response |
| Cannot roll back within 15 min | Engage deployment team | #releases |

## Post-Incident Review

**What went well:**
- Canary analysis caught the spike in 3 min, limiting blast radius to 10% of traffic
- Rollback was clean and fast — stable pods took full traffic without disruption

**What needs improvement:**
- ConfigMap schema change not documented in release notes or deployment checklist
- Staging routing config too simplified to catch prod-specific schema differences
- No schema validation step in the deployment pipeline for ConfigMaps

**Contributing factors (beyond root cause):**
- v4.1.0 changed `routeConfig` schema but ConfigMap not updated in sync
- No null guard in new routing code for old config format
- Staging config does not mirror prod structure

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Roll back canary, restore full stable traffic | Marcus Webb | 2026-04-18 | Done |
| Add ConfigMap schema validation to deployment pipeline | Platform team | 2026-05-02 | Open |
| Update staging routing config to mirror prod structure | SRE team | 2026-05-02 | Open |
| Document ConfigMap schema changes as required field in release notes | Marcus Webb | 2026-05-02 | Open |

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]]
- Related incidents: [[INC-011-rollback-failed-frontend]]
- PR/commit: N/A (rollback — v4.1.0 requeued for next window with updated ConfigMap)
- Post-mortem doc: N/A
