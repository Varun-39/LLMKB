---
id: INC-002
title: API Gateway OOMKilled — Heap Exhaustion
severity: SEV-2
service: api-gateway
environment: prod
category: outage
date: 2026-05-28
duration: "34m"
detection_gap: "2m"
tags:
  - incident
  - kubernetes
  - oom
  - memory
  - high
  - prod
  - api
error_family: oom
resolution_runbook: RB-002
resolution_outcome: resolved
---

## Summary

Two of three api-gateway pods were OOMKilled in the prod cluster at 14:23 UTC on 2026-05-28. The remaining pod absorbed full traffic, causing elevated latency and partial request drops. Service partially degraded for 34 minutes before all replicas were restored with an increased memory limit.

## Symptoms

- Grafana: `api-gateway` heap memory at 100% across 2 pods at 14:21 UTC
- Datadog: P95 latency on `/api/checkout` rose from 180 ms to 2.4 s
- PagerDuty alert: `APIGateway-PodOOMKilled` at 14:23 UTC
- ~8% of requests returning HTTP 502 (bad gateway from load balancer)
- Sentry: `java.lang.OutOfMemoryError: GC overhead limit exceeded`

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~4,100 concurrent users during peak window |
| Services degraded | api-gateway (partial), checkout-service (degraded via gateway) |
| Revenue impact | ~$12K in dropped or timed-out checkout sessions |
| Duration | 14:23 → 14:57 UTC (34 min) |
| Data loss | None |
| SLA breach | No — partial degradation stayed within SLA threshold |
| Customer comms | N/A — partial degradation, no status page update |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 14:21 | Heap memory at 100% on 2 pods (per Grafana) |
| 14:23 | Pods OOMKilled; alert fired |
| 14:24 | On-call acknowledged (James Okafor) |
| 14:30 | Root cause identified — unbounded ResponseCacheStore |
| 14:38 | Memory limit increased to 1.5Gi, rollout restart |
| 14:50 | Hotfix v3.8.1 deployed with cache eviction |
| 14:57 | All 3 pods running, heap stable at ~45% |

## Diagnosis

1. Confirmed OOMKilled pods
   ```bash
   kubectl get pods -n gateway -l app=api-gateway
   kubectl describe pod api-gateway-7d9f6-xk2p -n gateway | grep -A4 "Last State"
   # Reason: OOMKilled
   ```

2. Checked memory limits
   ```bash
   kubectl get deploy api-gateway -n gateway \
     -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'
   # 768Mi
   ```

3. Reviewed Grafana heap trend — linear growth over 45 min pre-crash, not a spike

4. Pulled thread + heap dump
   ```bash
   kubectl cp gateway/api-gateway-7d9f6-ab1q:/tmp/heapdump.hprof ./hd-api-gw-0528.hprof
   ```

5. Eclipse MAT: `ResponseCacheStore` retaining 14,000 entries, ~580 MB

6. Correlated with reporting-service bulk calls — 3× higher than baseline since 13:40 UTC

## Resolution

1. **Mitigate:** Increased memory limit to 1.5Gi to stabilize
   ```bash
   kubectl set resources deployment/api-gateway -n gateway --limits=memory=1.5Gi
   kubectl rollout restart deployment/api-gateway -n gateway
   ```

2. **Fix:** Patched `ResponseCacheStore` max-size to 2,000 entries (PR #2201, deployed v3.8.1-hotfix)
   ```bash
   kubectl set image deployment/api-gateway -n gateway \
     api-gateway=registry.internal/api-gateway:v3.8.1-hotfix
   ```

3. **Verify:** Confirmed all 3 pods Running and heap stable at ~45%
   ```bash
   kubectl top pods -n gateway -l app=api-gateway
   curl -s https://api.internal/health | jq .status
   # "healthy"
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Error rate >5% after 10 min | Escalate to senior on-call | PagerDuty |
| All replicas OOMKilled | Page EM + IC | #incident-response |
| Revenue systems impacted >30 min | Engage checkout and payment leads | Direct page |

## Post-Incident Review

**What went well:**
- Alerting caught crash within 2 min
- Heap dump available immediately due to pre-configured JVM flags

**What needs improvement:**
- Memory limits not reviewed since initial provisioning
- No alert on sustained heap >80% before crash

**Contributing factors (beyond root cause):**
- `ResponseCacheStore` had no max entry limit or eviction policy
- Reporting-service bulk calls increased cache fill rate 3× above baseline
- Memory limit (768Mi) unchanged for 6 months despite traffic growth

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Deploy hotfix with cache eviction | James Okafor | 2026-05-28 | Done |
| Add alert: heap >80% sustained 5 min | SRE team | 2026-06-11 | Open |
| Review all service memory limits quarterly | Platform team | 2026-06-11 | Open |
| Rate-limit bulk requests from reporting-service | James Okafor | 2026-06-11 | Open |

## Links

- Runbooks: [[RB-002-kubernetes-oom-remediation]]
- Related incidents: [[INC-001-payment-service-oom-crash]]
- PR/commit: PR #2201 (cache eviction hotfix)
- Post-mortem doc: N/A
