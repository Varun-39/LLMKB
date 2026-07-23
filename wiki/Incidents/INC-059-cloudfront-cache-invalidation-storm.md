---
id: INC-059
title: CloudFront Cache Invalidation Storm Overwhelmed Origin
severity: SEV-2
service: frontend
environment: prod
category: degradation
date: 2026-05-25
duration: "20m"
tags:
  - incident
  - cloudfront
  - cdn
  - cache
  - origin
  - traffic
  - high
  - prod
error_family: high-cpu
resolution_runbook: RB-006
resolution_outcome: resolved
---

## Summary

A deployment script issued a wildcard CloudFront invalidation (`/*`) instead of invalidating only changed assets. The CDN purged 100% of cached content simultaneously, causing all requests to hit the origin server directly. The origin (a small nginx pod serving static assets) was sized for 5% of total traffic (cache miss rate) and collapsed under 100% direct load, returning 503s for 20 minutes until caches refilled.

## Symptoms

- Frontend: intermittent 503 errors, slow page loads
- CloudFront: cache hit ratio dropped from 95% to 0% instantly
- Origin nginx pod: CPU at 100%, request queue overflowing
- CloudWatch: `5xxErrorRate` spike on CloudFront distribution

## Diagnosis

1. Confirmed cache miss rate
   ```bash
   aws cloudwatch get-metric-statistics --namespace AWS/CloudFront \
     --metric-name CacheHitRate --period 60 --statistics Average
   # 0% (was 95%)
   ```

2. Found deployment script issued `/*` invalidation
   ```bash
   aws cloudfront list-invalidations --distribution-id E1234
   # Invalidation path: /* created at deploy time
   ```

3. Origin pod overwhelmed
   ```bash
   kubectl top pods -n frontend -l app=static-assets
   # 980m/1000m CPU, 128 queued connections
   ```

## Resolution

1. **Mitigate:** Scaled origin pods from 2 to 10 temporarily
   ```bash
   kubectl scale deployment/static-assets -n frontend --replicas=10
   ```

2. **Fix:** Caches refilled naturally over 15 minutes; changed deploy script to only invalidate `/assets/<build-hash>/*`

3. **Verify:** Cache hit rate back to 95%, origin load back to baseline

## Post-Incident Review

- Wildcard invalidation (`/*`) should never be used in production
- Changed deploy script to invalidate only specific changed paths
- Sized origin to handle 25% cache miss rate (survivable burst)
- Added alert: if cache hit rate drops below 50% in 5 minutes, page immediately

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]]
- Related incidents: [[INC-010-release-failed-canary-api]]
