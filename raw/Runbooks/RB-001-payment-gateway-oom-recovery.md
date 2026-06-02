---
id: RB-001
title: Payment Gateway OOM Recovery
service: payment-gateway
severity: SEV-1
environment: prod
category: resource-exhaustion
status: active
owner: Priya Sharma
created: 2026-06-02
updated: 2026-06-02
last-updated: 2026-06-02
tags:
  - runbook
  - kubernetes
  - memory
  - oom
  - critical
  - prod
  - payments
related_incidents:
  - "[[INC-001-payment-service-oom-crash]]"
related_runbooks:
  - "[[RB-005-kubernetes-pod-crashloop-generic]]"
---

## Purpose

Diagnose and recover from OOM crashes in the payment-gateway service on Kubernetes. Covers immediate stabilization, root cause identification, and safe restoration of transaction processing.

## Scope

| | |
|---|---|
| **Service** | payment-gateway |
| **Environments** | prod, staging |
| **Use when** | Pods are OOMKilled or CrashLoopBackOff with memory pressure |
| **Do NOT use when** | Crash reason is liveness probe failure without OOM (check `kubectl describe pod`) |

## Prerequisites

- [x] `kubectl` access to `payments` namespace (prod cluster)
- [x] VPN connected
- [x] Grafana: `Payment Gateway - Resources` dashboard accessible
- [x] On-call confirmed in PagerDuty

## Required Tools

| Tool | Purpose |
|------|---------|
| `kubectl` (prod credentials) | Pod ops, logs, resource adjustment |
| Grafana | Memory/CPU trends |
| AWS ECR | Verify rollback image tags |
| Eclipse MAT | Heap dump analysis |
| Git (`payment-gateway` repo) | Cherry-pick hotfixes |

## Triggers

- Alert: `PaymentGateway-PodCrashLooping`
- Alert: `PaymentGateway-MemoryUsageHigh` (>85% for 5 min)
- Symptom: HTTP 503 on `/api/v2/payments/process`
- Metric: Container memory >90% of limit

## Triage

1. Confirm OOMKilled (not another crash reason)
   ```bash
   kubectl get pods -n payments -l app=payment-gateway
   kubectl describe pod <pod-name> -n payments | grep -A3 "Last State"
   # Expect: Reason: OOMKilled
   ```

2. Check blast radius — one pod or all replicas
   ```bash
   kubectl get pods -n payments -l app=payment-gateway -o wide
   ```

3. Note current memory limit
   ```bash
   kubectl get deploy payment-gateway -n payments \
     -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'
   ```

4. Not OOMKilled? → Use [[RB-005-kubernetes-pod-crashloop-generic]]

## Investigate

1. **Memory trend** — open Grafana dashboard
   - Linear growth = leak; sudden spike = load-induced

2. **Recent deployments**
   ```bash
   kubectl rollout history deployment/payment-gateway -n payments
   ```

3. **OOM evidence in logs**
   ```bash
   kubectl logs -l app=payment-gateway -n payments --tail=500 --previous \
     | grep -i "outofmemory\|heap\|gc overhead"
   ```

4. **Heap dump available?**
   ```bash
   kubectl exec <pod> -n payments -- ls /tmp/heapdump.hprof 2>/dev/null && echo "exists"
   ```

5. **Traffic volume** — rule out load-induced OOM
   ```bash
   kubectl logs -l app=payment-gateway -n payments --tail=100 \
     | grep "POST /api/v2/payments" | wc -l
   ```

6. **GC logs** (if enabled)
   ```bash
   kubectl logs <pod> -n payments --previous | grep "GC\|pause"
   ```

## Resolve

1. **Increase memory limit** to stabilize
   ```bash
   kubectl set resources deployment/payment-gateway -n payments \
     --limits=memory=2Gi --requests=memory=1Gi
   ```

2. **Restart deployment** to clear accumulated state
   ```bash
   kubectl rollout restart deployment/payment-gateway -n payments
   ```

3. **Wait for rollout** (3 min timeout)
   ```bash
   kubectl rollout status deployment/payment-gateway -n payments --timeout=180s
   ```

4. **If leak confirmed** — rollback to last good version
   ```bash
   kubectl rollout undo deployment/payment-gateway -n payments --to-revision=<N>
   ```

5. **If cache-related** — deploy targeted hotfix
   ```bash
   kubectl set image deployment/payment-gateway -n payments \
     payment-gateway=registry.internal/payment-gateway:<hotfix-tag>
   ```

6. **Monitor 15 min** on Grafana:
   - Memory stable below 70% of limit
   - Zero new OOMKilled events
   - Transaction success rate recovering

## Verify

- [ ] All pods Running, 0 restarts in 10 min
- [ ] Memory stable <70% of limit
- [ ] Error rate on `/api/v2/payments/process` < 0.1%
- [ ] No new PagerDuty alerts in 15 min
- [ ] Health check passing

```bash
kubectl get pods -n payments -l app=payment-gateway
curl -s -o /dev/null -w "%{http_code}" https://payments.internal/health
# Expect: 200
```

## Rollback

1. **Undo memory increase** (if causing node pressure)
   ```bash
   kubectl set resources deployment/payment-gateway -n payments \
     --limits=memory=1Gi --requests=memory=512Mi
   ```

2. **Undo hotfix deployment**
   ```bash
   kubectl rollout undo deployment/payment-gateway -n payments
   ```

3. **Full rollback** to last stable revision
   ```bash
   kubectl rollout undo deployment/payment-gateway -n payments --to-revision=<N>
   ```

4. Post in #incident-response: "Rollback executed, monitoring recovery"

## Escalation

| Trigger | Escalate to | Channel |
|---------|-------------|---------|
| Still crashing after memory bump + restart | Senior on-call + Platform | #incident-response |
| No resolution in 30 min | Engineering Manager | PagerDuty escalation |
| Leak confirmed, no hotfix available | Service owner (Priya Sharma) | Direct page |
| Node-level resource exhaustion | Platform/SRE | #platform-support |

## Notes

- JVM configured `-Xmx768m` inside 1Gi container. Gap covers off-heap + metaspace.
- If raising limit above 2Gi, verify node capacity — pods run on `c5.xlarge` (8Gi total).
- Historical: 3/4 past OOM incidents traced to unbounded caches. Check cache sizes first.
- Last tested: 2026-06-02
- Review cycle: Quarterly

## Links

- Incidents: [[INC-001-payment-service-oom-crash]]
- Related: [[RB-005-kubernetes-pod-crashloop-generic]]
