---
id: INC-045
title: NGINX Ingress Controller OOM from Oversized Request Headers
severity: SEV-1
service: ingress-controller
environment: prod
category: outage
date: 2026-04-15
duration: "12m"
tags:
  - incident
  - nginx
  - ingress
  - oom
  - kubernetes
  - critical
  - prod
---

## Summary

At 19:30 UTC on 2026-04-15, the NGINX ingress controller pods OOMKilled after a partner integration began sending requests with 256KB JWT tokens in the Authorization header. The default `proxy_buffer_size` of 4KB caused NGINX to allocate large temporary buffers for each oversized request, exhausting the 512MB container memory limit within 3 minutes under load. All ingress traffic was dropped for 12 minutes.

## Symptoms

- PagerDuty: `Ingress-PodCrashLooping` at 19:33 UTC
- All external HTTP traffic: 502 Bad Gateway
- NGINX error logs: `upstream sent too big header while reading response`
- Pod status: OOMKilled, CrashLoopBackOff
- Partner API calls: all carrying 256KB Authorization headers

## Diagnosis

1. Confirmed OOMKilled
   ```bash
   kubectl describe pod nginx-ingress-xyz -n ingress-system | grep -A3 "Last State"
   # Reason: OOMKilled, Exit Code: 137
   ```

2. NGINX error logs before crash
   ```bash
   kubectl logs nginx-ingress-xyz -n ingress-system --previous --tail=50
   # "upstream sent too big header", "worker process exiting"
   # Large buffer allocations for oversized headers
   ```

3. Identified partner requests with massive headers
   ```bash
   # Access logs showed requests from partner IP with 256KB Authorization header
   ```

## Resolution

1. **Mitigate:** Increased memory limit to 1Gi and restarted
   ```bash
   kubectl set resources deployment/nginx-ingress -n ingress-system --limits=memory=1Gi
   kubectl rollout restart deployment/nginx-ingress -n ingress-system
   ```

2. **Fix:** Added `proxy_buffer_size 16k` and `large_client_header_buffers 4 16k` to NGINX config; added `client_header_buffer_size` limit of 64KB to reject oversized headers

3. **Verify:** Ingress pods stable, traffic flowing

## Post-Incident Review

- Default NGINX buffer settings insufficient for large JWT tokens
- Added request header size limit (64KB max) at ingress level
- Partner notified to reduce token size or use token exchange pattern
- Increased ingress controller memory limit permanently to 1Gi

## Links

- Runbooks: [[RB-002-kubernetes-oom-remediation]]
- Related incidents: [[INC-002-k8s-oom-api-pod]]
