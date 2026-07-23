---
id: INC-077
title: DNS NXDOMAIN Due to CoreDNS Cache Poisoning
severity: SEV-1
service: coredns
environment: prod
category: outage
date: 2026-01-28
duration: "38m"
tags:
  - incident
  - dns
  - coredns
  - kubernetes
  - networking
error_family: dns-nxdomain
resolution_runbook: RB-018
resolution_outcome: resolved
---

## Summary

A misconfigured upstream DNS server returned NXDOMAIN responses for internal service names which CoreDNS cached aggressively. This caused all in-cluster DNS resolution to fail for affected services for 38 minutes, resulting in widespread HTTP 503 errors across the platform.

## Symptoms

- Multiple services reporting `dial tcp: lookup payment-gateway.prod.svc.cluster.local: no such host`
- CoreDNS logs: `NXDOMAIN for payment-gateway.prod.svc.cluster.local from upstream 10.0.0.2`
- PagerDuty: `DNS-Resolution-Failure-Critical` across 15 services
- nslookup from pods returning NXDOMAIN for valid cluster services
- Grafana: DNS query success rate dropped from 99.99% to 12%

## Diagnosis

1. Confirmed DNS failures via `kubectl exec -it debug-pod -- nslookup payment-gateway.prod.svc.cluster.local`
2. Checked CoreDNS pods — healthy and running
3. Inspected CoreDNS Corefile — found upstream forwarder pointed to `10.0.0.2` which was returning NXDOMAIN for cluster-local queries due to a misconfigured conditional forward zone
4. CoreDNS negative cache TTL was set to 300s, so poisoned entries persisted even after upstream was fixed
5. Root cause: network team updated upstream resolver `10.0.0.2` config without coordinating with platform team

## Resolution

1. Flushed CoreDNS cache by restarting pods: `kubectl rollout restart deployment coredns -n kube-system`
2. Added explicit forward zone for `.cluster.local` to prevent upstream leakage
3. Reduced negative cache TTL to 5s in Corefile: `cache 30 { denial 5 }`
4. Verified DNS resolution restored across all namespaces

## Post-Incident Review

Implemented split-horizon DNS policy preventing cluster-local queries from reaching upstream resolvers. Added CoreDNS NXDOMAIN rate monitoring. Established change coordination requirement between network and platform teams.

## Links
- Related: [[RB-018-dns-resolution-failure]]
