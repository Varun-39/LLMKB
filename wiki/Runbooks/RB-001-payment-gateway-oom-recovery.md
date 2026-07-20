---
id: RB-001
title: Payment Gateway OOM Recovery
service: payment-gateway
related_services:
  - api-gateway
  - payment-processor
severity: SEV-1
environment: prod
category: resource-exhaustion
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
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
  - "[[RB-002-kubernetes-oom-remediation]]"
  - "[[RB-007-pod-crash-investigation]]"
related_guardrails: []
---

## Purpose

Diagnose and recover from OOM crashes in the payment-gateway service on Kubernetes, covering immediate stabilization, root cause identification, and safe restoration of transaction processing.

**Desired outcome:** All payment-gateway pods running stably with memory usage below 70% of limit and transaction success rate at pre-incident baseline.

## Success Criteria

Before closing the incident or declaring the runbook complete, ALL of the following must be true:

- Error rate on `/api/v2/payments/process` < 0.1%
- Memory usage stable below 70% of container limit for at least 15 minutes
- No active PagerDuty alerts for payment-gateway for at least 15 minutes
- Health endpoint (`/health`) returning 200
- Zero new OOMKilled events in the last 15 minutes

## Scope

| Attribute | Value |
|-----------|-------|
| Service | payment-gateway |
| Related services | api-gateway, payment-processor |
| Environments | prod, staging |
| Use when | Pods are OOMKilled or CrashLoopBackOff with memory pressure |
| Do NOT use when | Crash reason is liveness probe failure without OOM (check `kubectl describe pod`) |
| Risk level | Medium |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to `payments` namespace (prod cluster)
- [ ] VPN connected
- [ ] Grafana: `Payment Gateway - Resources` dashboard accessible
- [ ] On-call role confirmed in PagerDuty
- [ ] Knowledge of current memory limits and recent deployments

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` (prod credentials) | Pod ops, logs, resource adjustment | Cluster admin |
| Grafana | Memory/CPU trends | Read access |
| AWS ECR | Verify rollback image tags | Read access |
| Eclipse MAT | Heap dump analysis | Local tool |
| Git (`payment-gateway` repo) | Cherry-pick hotfixes | Write access |

## Trigger

- Alert: `PaymentGateway-PodCrashLooping` fires in PagerDuty
- Alert: `PaymentGateway-MemoryUsageHigh` (>85% for 5 min)
- Symptom: HTTP 503 on `/api/v2/payments/process`
- Metric: Container memory >90% of limit

## Triage

1. Confirm OOMKilled (not another crash reason)
   ```bash
   kubectl get pods -n payments -l app=payment-gateway
   kubectl describe pod <pod-name> -n payments | grep -A3 "Last State"
   # What to look for: Reason: OOMKilled, Exit Code: 137
   ```

2. Assess blast radius — one pod or all replicas
   ```bash
   kubectl get pods -n payments -l app=payment-gateway -o wide
   ```

3. Note current memory limit
   ```bash
   kubectl get deploy payment-gateway -n payments \
     -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'
   ```

4. Wrong symptoms? Not OOMKilled? → Try [[RB-007-pod-crash-investigation]]

## Investigation

1. **Check memory trend** — open Grafana dashboard `Payment Gateway - Resources`
   ```bash
   # Visual check in Grafana
   # What to look for: Linear growth = leak; sudden spike = load-induced
   ```

2. **Correlate with recent deployments**
   ```bash
   kubectl rollout history deployment/payment-gateway -n payments
   # What to look for: new revision deployed around the same time as OOM start
   ```

3. **Check OOM evidence in logs**
   ```bash
   kubectl logs -l app=payment-gateway -n payments --tail=500 --previous \
     | grep -i "outofmemory\|heap\|gc overhead"
   ```

4. **Check for heap dump**
   ```bash
   kubectl exec <pod> -n payments -- ls /tmp/heapdump.hprof 2>/dev/null && echo "exists"
   ```

5. **Rule out load-induced OOM — check traffic volume**
   ```bash
   kubectl logs -l app=payment-gateway -n payments --tail=100 \
     | grep "POST /api/v2/payments" | wc -l
   ```

6. **Check GC logs** (if enabled)
   ```bash
   kubectl logs <pod> -n payments --previous | grep "GC\|pause"
   ```

7. **Decision point:**
   - IF linear memory growth → memory leak confirmed → proceed to Mitigation Option A + Option D
   - IF sudden spike correlating with traffic → load-induced → proceed to Mitigation Option A
   - IF recent deployment correlates → bad release → proceed to Mitigation Option D
   - IF unclear → escalate (see Escalation section)

## Mitigation

### Option A: Increase memory limit (buys time)

```bash
kubectl set resources deployment/payment-gateway -n payments \
  --limits=memory=2Gi --requests=memory=1Gi
```

### Option B: Restart deployment (clear accumulated state)

```bash
kubectl rollout restart deployment/payment-gateway -n payments
kubectl rollout status deployment/payment-gateway -n payments --timeout=180s
```

### Option C: Deploy targeted hotfix (if cache-related)

```bash
kubectl set image deployment/payment-gateway -n payments \
  payment-gateway=registry.internal/payment-gateway:<hotfix-tag>
```

### Option D: Rollback to last good version (if leak confirmed in new release)

```bash
kubectl rollout undo deployment/payment-gateway -n payments --to-revision=<N>
```

**After mitigation:** Monitor for 15 minutes on Grafana — memory stable below 70%, zero new OOMKilled events, transaction success rate recovering.

## Verification

- [ ] All pods Running, 0 restarts in 10 minutes
- [ ] Memory stable below 70% of limit
- [ ] Error rate on `/api/v2/payments/process` < 0.1%
- [ ] No new PagerDuty alerts in 15 minutes
- [ ] Health check passing

```bash
kubectl get pods -n payments -l app=payment-gateway
curl -s -o /dev/null -w "%{http_code}" https://payments.internal/health
# Expected: 200
```

## Failure Signals

If the mitigation did NOT work, you will observe one or more of the following:

- Memory usage continues climbing toward the new limit within 15 minutes
- New OOMKilled events appear despite increased limits
- Transaction error rate does not decrease within 5 minutes
- Pods enter CrashLoopBackOff again after restart
- Health endpoint still returning non-200 status

**If any failure signal is present after mitigation:** Do NOT repeat the same step. Proceed to Rollback or Escalation immediately.

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

4. Notify #incident-response: "Rollback executed — escalating."

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Still crashing after memory bump + restart | Senior on-call + Platform | #incident-response | 5 min response |
| No resolution in 30 min | Engineering Manager | PagerDuty escalation | Immediate |
| Leak confirmed, no hotfix available | Service owner (Priya Sharma) | Direct page | 10 min response |
| Node-level resource exhaustion | Platform/SRE | #platform-support | 10 min response |

## Notes

- JVM configured `-Xmx768m` inside 1Gi container. Gap covers off-heap + metaspace.
- If raising limit above 2Gi, verify node capacity — pods run on `c5.xlarge` (8Gi total).
- Historical: 3/4 past OOM incidents traced to unbounded caches. Check cache sizes first.
- See also: [[INC-001-payment-service-oom-crash]], [[RB-002-kubernetes-oom-remediation]]

## Maintenance

- **Last tested:** 2026-06-02
- **Review cycle:** Quarterly
- **Next review:** 2026-09-02
- **Test method:** Chaos engineering — inject memory pressure via stress-ng in staging, execute runbook steps.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-02 | Priya Sharma | Initial publication |
| 2026-06-12 | SRE Team | Migrated to new runbook template format |
