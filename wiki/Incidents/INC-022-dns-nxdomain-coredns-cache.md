---
id: INC-022
title: DNS NXDOMAIN Due to CoreDNS Cache Poisoning
severity: SEV-1
service: coredns
environment: prod
category: outage
date: 2026-01-14
duration: "38m"
tags:
  - incident
  - dns
  - kubernetes
  - coredns
  - networking
  - critical
---

## Summary

Internal service discovery failed across the production Kubernetes cluster after a CoreDNS cache became poisoned with stale NXDOMAIN responses. All inter-service communication relying on cluster DNS returned `NXDOMAIN` for valid service names. Root cause: upstream DNS resolver returned negative cache entries with an excessively high TTL during a brief upstream outage, and CoreDNS propagated them.

## Symptoms

- Widespread `could not resolve host` errors across multiple services
- PagerDuty: `ServiceDiscovery-DNSFailure` on 14 services simultaneously
- `nslookup payment-gateway.payments.svc.cluster.local` returning `NXDOMAIN`
- Grafana: DNS query success rate dropped from 99.99% to 12%
- Application logs: `java.net.UnknownHostException`, `getaddrinfo ENOTFOUND`

## Diagnosis

1. Confirmed DNS resolution failure from within pods:
   ```bash
   kubectl exec -it debug-pod -- nslookup kubernetes.default.svc.cluster.local
   # Server: 10.96.0.10, Answer: ** server can't find kubernetes.default: NXDOMAIN
   ```
2. CoreDNS logs showed cached negative responses:
   ```
   [INFO] 10.244.3.15:41823 - 12345 "A IN payment-gateway.payments.svc.cluster.local. udp 67 false 512" NXDOMAIN qr,aa,rd 162 0.000284s
   ```
3. Upstream resolver (10.0.0.2) had returned NXDOMAIN with TTL=3600 during a 2-minute outage
4. CoreDNS `cache` plugin honored the negative TTL without cap

## Resolution

1. Flushed CoreDNS cache by restarting all CoreDNS pods:
   ```bash
   kubectl rollout restart deployment coredns -n kube-system
   ```
2. Verified DNS resolution recovered within 30 seconds post-restart
3. Added `denial 30` to CoreDNS Corefile to cap negative cache TTL:
   ```
   cache 30 {
       denial 30
   }
   ```
4. Applied updated ConfigMap and triggered rolling restart

## Post-Incident Review

- Negative cache TTL was unbounded — upstream could poison for hours
- Added monitoring: alert if DNS NXDOMAIN rate exceeds 5% for 60 seconds
- Added CoreDNS `denial` cap to all clusters
- Documented in runbook for future occurrences

## Links

- Related: [[RB-018-dns-resolution-failure]]
