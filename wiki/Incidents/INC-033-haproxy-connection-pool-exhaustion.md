---
id: INC-033
title: HAProxy Connection Pool Exhaustion
severity: SEV-1
service: load-balancer
environment: prod
category: capacity
date: 2026-04-01
duration: "22m"
tags:
  - incident
  - haproxy
  - load-balancer
  - connections
  - exhaustion
  - networking
  - critical
---

## Summary

HAProxy reached its `maxconn` limit (50,000) causing all new TCP connections to queue and timeout. Root cause: a downstream service (`search-api`) became slow (10s response times), causing connections to accumulate instead of completing. All services behind the load balancer were affected for 22 minutes.

## Symptoms

- External monitoring: HTTP 503 on all endpoints
- HAProxy stats: `scur` (sessions current) at 50,000 (maxconn limit)
- HAProxy logs: `[WARNING] ... backend search-api has no server available`
- Backend queue depth: 12,000+ pending connections
- Client-side: `Connection timed out` after 30s

## Diagnosis

1. Checked HAProxy stats socket:
   ```bash
   echo "show stat" | socat stdio /var/run/haproxy.sock | grep search-api
   # qcur=12482, scur=50000, slim=50000
   ```
2. `search-api` backend health checks passing (responds, just slowly)
3. Each search-api request taking 8-12s instead of normal 200ms
4. Connections pile up: 50K slots filled in minutes at that response time
5. Root cause on search-api: Elasticsearch cluster had a long GC pause due to heap pressure

## Resolution

1. Reduced traffic to search-api by setting weight to 0 temporarily:
   ```bash
   echo "set weight search-api/srv1 0" | socat stdio /var/run/haproxy.sock
   ```
2. Connections drained within 30 seconds, freeing slots for other backends
3. Fixed Elasticsearch: forced a full GC and restarted the slow node
4. Gradually restored search-api weight
5. Added `timeout server 5s` for search-api backend (was 60s)

## Post-Incident Review

- One slow backend can exhaust the entire load balancer
- Added per-backend `maxconn` limits (search-api: 5000, others: proportional)
- Reduced backend timeout from 60s to 5s for search endpoints
- Added alert: `haproxy_connections_current > 80% of maxconn`

## Links

- Related: [[RB-020-haproxy-connection-saturation-recovery]]
