---
id: INC-082
title: Nginx Upstream Keepalive Exhaustion Causing 502 Errors
severity: SEV-2
service: api-gateway
environment: prod
category: degradation
date: 2026-04-05
duration: "20m"
tags:
  - incident
  - nginx
  - keepalive
  - upstream
  - 502
  - api-gateway
  - prod
---

## Summary

An increase in concurrent API traffic exhausted the nginx upstream keepalive connection pool, causing nginx to fail opening new upstream connections and return 502 Bad Gateway errors. The `keepalive` directive was set to a default of 32 connections per worker — far below the required capacity during peak traffic.

## Symptoms

- nginx error log: `upstream: no live upstreams while connecting to upstream`
- HTTP 502 error rate: 12% of all API requests
- `nginx_upstream_responses_total{status="502"}` spiking in Prometheus
- Upstream backend pods healthy (responding normally on direct access)

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~8,000 API calls failed |
| Services degraded | api-gateway (all upstream services intermittently) |
| Revenue impact | ~$2.1K |
| Duration | 16:40 → 17:00 UTC (20 min) |
| Data loss | None |
| SLA breach | No |
| Customer comms | N/A — error rate below status page threshold |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 16:35 | Traffic spike from mobile app push notification |
| 16:40 | 502 error alert fired (>5%) |
| 16:45 | On-call identified nginx keepalive limit |
| 16:52 | Config updated and nginx reloaded |
| 17:00 | Error rate back to baseline |

## Diagnosis

1. Confirmed 502s are nginx-side, not backend:
   ```bash
   curl -v http://backend-svc:8080/health
   # HTTP/1.1 200 OK — backends healthy
   ```
2. Checked nginx error log:
   ```bash
   tail -50 /var/log/nginx/error.log
   # upstream: no live upstreams while connecting to upstream
   ```
3. Checked keepalive setting:
   ```bash
   grep keepalive /etc/nginx/conf.d/upstream.conf
   # keepalive 32;
   ```
4. Checked active connections vs limit:
   ```bash
   nginx -T | grep worker_connections
   # worker_connections 1024; (4 workers = 4096 max)
   # keepalive 32 per worker = 128 total — clearly insufficient at peak
   ```

## Resolution

1. **Fix:** Updated nginx upstream keepalive in ConfigMap
   ```bash
   kubectl edit configmap nginx-config -n api-gateway
   # Changed: keepalive 32  →  keepalive 256
   ```
2. **Reloaded nginx without downtime:**
   ```bash
   kubectl exec -n api-gateway nginx-pod -- nginx -s reload
   ```
3. **Verify:**
   ```bash
   watch -n2 'kubectl exec -n api-gateway nginx-pod -- curl -s localhost/nginx_status'
   # Active connections drop, 502s cease
   ```

## Post-Incident Review

**What went well:**
- Fast root cause — nginx metrics clearly pointed to upstream connection exhaustion

**What needs improvement:**
- Default keepalive value never reviewed after traffic growth
- No load-based tuning in nginx config review process

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Set keepalive to 256 in all nginx upstream blocks; document tuning formula | Platform | 2026-04-12 | Open |
| Add `nginx_upstream_keepalive` gauge to SLO dashboard | Observability | 2026-04-12 | Open |

## Links

- Runbooks: [[RB-026-ingress-controller-troubleshooting]]
- Related incidents: [[INC-033-haproxy-connection-pool-exhaustion]]
