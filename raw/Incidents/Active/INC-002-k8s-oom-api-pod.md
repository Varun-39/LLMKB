---
id: INC-002
title: API Gateway OOMKilled — Heap Exhaustion
severity: SEV-2
service: api-gateway
environment: prod
category: outage
status: resolved
owner: James Okafor
assigned-to: James Okafor
date: 2026-05-28
duration: 34 minutes
created: 2026-05-28
updated: 2026-05-28
tags:
  - incident
  - kubernetes
  - oom
  - memory
  - high
  - prod
  - api
related_runbooks:
  - "[[RB-001-kubernetes-oom]]"
related_incidents:
  - "[[INC-001-payment-service-oom-crash]]"
---

# INC-002 — API Gateway OOMKilled: Heap Exhaustion

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

## Possible Causes

1. **Unbounded response cache** — request/response cache not evicting older entries
2. **Spike in payload size** — large bulk API calls from reporting-service inflating heap
3. **Memory limit too low** — limit unchanged since initial deployment 6 months ago despite traffic growth
4. **GC tuning mismatch** — CMS collector causing long stop-the-world pauses and apparent OOM

## Troubleshooting Steps

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

1. Increased memory limit to 1.5Gi to stabilize
   ```bash
   kubectl set resources deployment/api-gateway -n gateway --limits=memory=1.5Gi
   kubectl rollout restart deployment/api-gateway -n gateway
   ```

2. Patched `ResponseCacheStore` max-size to 2,000 entries (PR #2201, deployed v3.8.1-hotfix)
   ```bash
   kubectl set image deployment/api-gateway -n gateway \
     api-gateway=registry.internal/api-gateway:v3.8.1-hotfix
   ```

3. Confirmed all 3 pods Running and heap stable at ~45%
   ```bash
   kubectl top pods -n gateway -l app=api-gateway
   curl -s https://api.internal/health | jq .status
   # "healthy"
   ```

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Error rate >5% after 10 min | Escalate to senior on-call | PagerDuty |
| All replicas OOMKilled | Page EM + IC | #incident-response |
| Revenue systems impacted >30 min | Engage checkout and payment leads | Direct page |

## Post-Incident Notes

**Went well:**
- Alerting caught crash within 2 min
- Heap dump available immediately due to pre-configured JVM flags

**Improve:**
- Memory limits not reviewed since initial provisioning
- No alert on sustained heap >80% before crash

**Action items:**
- [x] Deploy hotfix with cache eviction
- [ ] Add alert: heap >80% sustained 5 min
- [ ] Review all service memory limits quarterly
- [ ] Rate-limit bulk requests from reporting-service

## Related Runbooks

- [[RB-001-kubernetes-oom]]
