---
id: INC-068
title: API Rate Limit Bypass via X-Forwarded-For Header Spoofing
severity: SEV-2
service: api-gateway
environment: prod
category: degradation
date: 2026-06-14
duration: "35m"
tags:
  - incident
  - security
  - rate-limit
  - header-spoofing
  - api
  - high
  - prod
---

## Summary

A malicious actor bypassed the API rate limiter by rotating the `X-Forwarded-For` header on each request. The rate limiter used client IP from XFF (trusting all hops) as the rate-limit key. By spoofing a different IP on each request, the attacker made 50,000 requests/minute to the `/api/search` endpoint, causing backend CPU saturation and degraded response times for all users.

## Symptoms

- api-gateway: P99 latency jumped from 200ms to 4s
- Search backend CPU: 98%
- Rate limiter: no single IP exceeding threshold (attacker distributed across spoofed IPs)
- Access logs: 50,000 req/min to `/api/search` from single source (varying XFF)

## Diagnosis

1. Identified traffic pattern
   ```bash
   kubectl logs -l app=api-gateway -n api --tail=1000 | grep "/api/search" | \
     awk '{print $1}' | sort | uniq -c | sort -rn | head -5
   # 50,000 requests from load balancer IP (real client hidden behind XFF)
   ```

2. XFF header spoofed: each request had a different XFF value
   ```bash
   # Access log: X-Forwarded-For: 203.0.113.{random} — rotating per request
   ```

3. Rate limiter trusting leftmost XFF address (attacker-controlled)

## Resolution

1. **Mitigate:** Added emergency rate limit on the load balancer's real connection IP
   ```bash
   # Added nginx limit_req based on $remote_addr (not XFF)
   kubectl patch configmap nginx-config -n ingress --type merge \
     -p '{"data":{"rate-limit-key":"$remote_addr"}}'
   kubectl rollout restart deployment/nginx-ingress -n ingress-system
   ```

2. **Fix:** Changed rate limit key to use only the rightmost trusted proxy hop

3. **Verify:** Attack traffic now rate-limited, latency recovered

## Post-Incident Review

- Never trust client-supplied `X-Forwarded-For` for security decisions
- Changed rate limit key to use connection IP from last trusted proxy
- Added WAF rule: requests with >5 XFF hops get blocked
- Added alert: if single endpoint receives >10,000 req/min regardless of source

## Links

- Runbooks: [[RB-008-network-saturation-throughput]]
- Related incidents: [[INC-007-high-cpu-payment-service]]
