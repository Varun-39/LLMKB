---
id: RB-018
title: DNS Resolution Failure (CoreDNS / External DNS)
service: coredns
related_services:
  - api-gateway
  - all-services
severity: SEV-1
environment: prod
category: connectivity
risk_level: medium
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - dns
  - coredns
  - networking
  - kubernetes
  - prod
related_incidents:
  - "[[INC-022-dns-nxdomain-coredns-cache]]"
  - "[[INC-024-coredns-cache-poisoning-nxdomain]]"
  - "[[INC-053-dns-ttl-cached-stale-endpoint]]"
related_runbooks:
  - "[[RB-008-network-saturation-throughput]]"
related_guardrails: []
---

## Purpose

Diagnose and resolve DNS resolution failures for both cluster-internal (CoreDNS) and external DNS lookups.

**Desired outcome:** All DNS resolution working — internal service discovery and external domain lookups returning correct results within 5ms.

## Success Criteria

- `nslookup kubernetes.default.svc.cluster.local` resolves correctly from pods
- External DNS resolution working (e.g., `nslookup google.com` from pods)
- CoreDNS pods running without errors
- DNS query latency <5ms for internal, <50ms for external
- No NXDOMAIN or SERVFAIL for valid domains

## Scope

| Attribute | Value |
|-----------|-------|
| Service | coredns |
| Related services | All services (DNS is foundational) |
| Environments | prod, staging |
| Use when | Services cannot resolve DNS names, NXDOMAIN for valid services |
| Do NOT use when | Network is completely down (check VPC/subnet first) |
| Risk level | Medium |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to `kube-system` namespace
- [ ] `dig`/`nslookup` available in a debug pod
- [ ] Access to CoreDNS ConfigMap

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | CoreDNS pod operations | Cluster admin |
| `dig`/`nslookup` | DNS query testing | Pod exec |
| CoreDNS logs | Error identification | Log access |

## Trigger

- Alert: `CoreDNS-ErrorsHigh`, `DNS-ResolutionFailed`
- Symptom: Services logging `UnknownHostException`, `NXDOMAIN`, `SERVFAIL`
- Symptom: Service discovery broken (pods can't reach other services by name)
- Metric: CoreDNS response latency spike or error rate increase

## Triage

1. Test DNS from a pod
   ```bash
   kubectl run dns-test --rm -it --image=busybox --restart=Never -- nslookup kubernetes.default
   # What to look for: should resolve to cluster IP. If fails → CoreDNS issue.
   ```

2. Check CoreDNS pods
   ```bash
   kubectl get pods -n kube-system -l k8s-app=kube-dns
   # What to look for: Running state, restart count
   ```

3. Check CoreDNS logs
   ```bash
   kubectl logs -l k8s-app=kube-dns -n kube-system --tail=50
   # What to look for: SERVFAIL, timeout, loop detected
   ```

## Investigation

1. **Internal DNS failure (service.namespace.svc.cluster.local)**
   ```bash
   kubectl exec <pod> -n <namespace> -- nslookup <service>.<namespace>.svc.cluster.local
   # If fails: CoreDNS config or pod issue
   ```

2. **External DNS failure (external domains)**
   ```bash
   kubectl exec <pod> -n <namespace> -- nslookup google.com
   # If internal works but external fails: upstream DNS or forward config
   ```

3. **Check CoreDNS ConfigMap**
   ```bash
   kubectl get configmap coredns -n kube-system -o yaml
   # What to look for: forward section pointing to correct upstream, no syntax errors
   ```

4. **Check if CoreDNS is overloaded**
   ```bash
   kubectl top pods -n kube-system -l k8s-app=kube-dns
   # What to look for: CPU/memory high = need more replicas
   ```

5. **Decision point:**
   - IF CoreDNS pods crashing → proceed to Mitigation Option A
   - IF config error → proceed to Mitigation Option B
   - IF overloaded → proceed to Mitigation Option C
   - IF upstream DNS issue → proceed to Mitigation Option D

## Mitigation

### Option A: CoreDNS pods crashing — restart

```bash
kubectl rollout restart deployment/coredns -n kube-system
```

### Option B: Fix CoreDNS ConfigMap

```bash
kubectl edit configmap coredns -n kube-system
# Fix the configuration (forward, cache, loop sections)
kubectl rollout restart deployment/coredns -n kube-system
```

### Option C: Scale CoreDNS (overloaded)

```bash
kubectl scale deployment/coredns -n kube-system --replicas=5
```

### Option D: Fix upstream DNS forwarding

```bash
kubectl edit configmap coredns -n kube-system
# Ensure forward section: forward . /etc/resolv.conf (or specific upstream like 8.8.8.8)
kubectl rollout restart deployment/coredns -n kube-system
```

**After mitigation:** Test DNS resolution from a debug pod.

## Verification

- [ ] Internal DNS resolves: `nslookup kubernetes.default.svc.cluster.local`
- [ ] External DNS resolves: `nslookup google.com`
- [ ] CoreDNS pods healthy
- [ ] No NXDOMAIN/SERVFAIL errors in CoreDNS logs
- [ ] Service-to-service communication restored

```bash
kubectl run dns-verify --rm -it --image=busybox --restart=Never -- sh -c "nslookup kubernetes.default && nslookup google.com"
# Expected: both resolve successfully
```

## Failure Signals

- DNS still failing after CoreDNS restart
- CoreDNS pods keep crashing
- Only specific namespaces affected (RBAC/NetworkPolicy issue)
- External resolution works but internal doesn't (or vice versa)

**If any failure signal is present:** Escalate.

## Rollback

1. **Undo ConfigMap change:** `kubectl rollout undo deployment/coredns -n kube-system`
2. **Undo scale:** `kubectl scale deployment/coredns -n kube-system --replicas=<original>`

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| All DNS broken cluster-wide | Platform team | PagerDuty P1 | Immediate |
| CoreDNS config corrupted | Platform team | #platform-support | 5 min |
| Upstream DNS provider issue | Network/infra team | #platform-support | 10 min |

## Notes

- **DNS is single point of failure.** If CoreDNS is down, everything is down.
- **ndots:5 default** causes 5 search domain attempts before external lookup. This amplifies DNS load.
- **CoreDNS loop detection plugin** can cause crashes if misconfigured. Check for `loop` in ConfigMap.
- **Negative caching (NXDOMAIN cache)** can make a resolved issue appear to persist. Wait for TTL or restart CoreDNS.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Scale CoreDNS to 0 in staging, verify detection and recovery.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Platform Team | Initial publication |
