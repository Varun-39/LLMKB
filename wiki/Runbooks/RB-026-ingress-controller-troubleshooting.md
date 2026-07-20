---
id: RB-026
title: Ingress Controller Troubleshooting (NGINX/ALB)
service: ingress-controller
related_services:
  - api-gateway
  - frontend
  - all-services
severity: SEV-1
environment: prod
category: connectivity
risk_level: high
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - ingress
  - nginx
  - alb
  - load-balancer
  - kubernetes
  - prod
related_incidents:
  - "[[INC-045-nginx-ingress-oom-large-headers]]"
  - "[[INC-048-aws-alb-target-deregistration-delay]]"
related_runbooks:
  - "[[RB-020-haproxy-connection-saturation-recovery]]"
  - "[[RB-002-kubernetes-oom-remediation]]"
related_guardrails: []
---

## Purpose

Diagnose and resolve ingress controller failures including 502/503/504 errors, configuration reload failures, and resource exhaustion.

**Desired outcome:** All ingress routes serving traffic, no error responses from ingress layer, configuration synced.

## Success Criteria

- HTTP error rate from ingress <0.1%
- Ingress controller pods running stably
- All Ingress resources synced (no config reload errors)
- Backend health checks passing
- Latency at baseline

## Scope

| Attribute | Value |
|-----------|-------|
| Service | ingress-controller |
| Related services | api-gateway, frontend, all externally-exposed services |
| Environments | prod, staging |
| Use when | 502/503/504 errors at ingress, config reload failures, ingress OOM |
| Do NOT use when | Backend service is down (fix the backend, not ingress) |
| Risk level | High (ingress down = all external traffic down) |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to ingress-system namespace
- [ ] Ingress controller logs accessible
- [ ] External monitoring confirming error rate

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Ingress pod operations | Cluster admin |
| `curl` | External endpoint testing | Local |
| NGINX/ALB logs | Error identification | Log access |

## Trigger

- Alert: `Ingress-ErrorRateHigh`, `Ingress-5xxSpike`
- Symptom: All external traffic returning 502/503/504
- Symptom: Ingress controller pods in CrashLoopBackOff/OOMKilled
- Symptom: New Ingress resources not taking effect

## Triage

1. Check ingress controller pods
   ```bash
   kubectl get pods -n ingress-system -l app.kubernetes.io/name=ingress-nginx
   # What to look for: Running, restart count, OOMKilled
   ```

2. Check for configuration errors
   ```bash
   kubectl logs -l app.kubernetes.io/name=ingress-nginx -n ingress-system --tail=50 | grep -i "error\|emerg\|failed"
   ```

3. Test from external
   ```bash
   curl -s -o /dev/null -w "%{http_code}" https://<domain>/health
   # 502/503 = ingress issue; timeout = pod/network issue
   ```

## Investigation

1. **NGINX config reload failure**
   ```bash
   kubectl exec <ingress-pod> -n ingress-system -- nginx -t
   # What to look for: syntax OK vs. configuration error
   ```

2. **Check which Ingress resource caused the error**
   ```bash
   kubectl get ingress --all-namespaces -o wide
   kubectl logs -l app.kubernetes.io/name=ingress-nginx -n ingress-system | grep "invalid\|error in"
   ```

3. **Check backend connectivity**
   ```bash
   kubectl exec <ingress-pod> -n ingress-system -- curl -s http://<backend-service>.<namespace>.svc:8080/health
   ```

4. **Decision point:**
   - IF OOMKilled → proceed to Mitigation Option A
   - IF config error → proceed to Mitigation Option B
   - IF backend unreachable → check backend service, not this runbook
   - IF intermittent 502 during deploys → proceed to Mitigation Option C

## Mitigation

### Option A: Ingress OOM — increase memory

```bash
kubectl set resources deployment/ingress-nginx-controller -n ingress-system --limits=memory=1Gi
kubectl rollout restart deployment/ingress-nginx-controller -n ingress-system
```

### Option B: Fix invalid configuration

```bash
# Identify the bad Ingress resource:
kubectl logs -l app.kubernetes.io/name=ingress-nginx -n ingress-system | grep "Ignoring ingress"
# Fix or delete the problematic Ingress:
kubectl delete ingress <bad-ingress> -n <namespace>
```

### Option C: Fix 502 during deployments (deregistration delay)

```bash
# Add preStop hook to backend pods:
# lifecycle.preStop.exec.command: ["sh", "-c", "sleep 15"]
# Reduce ALB deregistration delay:
kubectl annotate ingress <name> -n <namespace> \
  alb.ingress.kubernetes.io/target-group-attributes="deregistration_delay.timeout_seconds=20"
```

**After mitigation:** Verify traffic flowing without errors.

## Verification

- [ ] External health check returning 200
- [ ] Error rate <0.1%
- [ ] Ingress pods stable
- [ ] All routes serving

```bash
curl -s -o /dev/null -w "%{http_code}" https://<domain>/health
# Expected: 200
kubectl get pods -n ingress-system | grep -v Running
# Expected: empty
```

## Failure Signals

- 502 errors persist after ingress restart
- Config reload keeps failing (new invalid Ingress being created)
- Ingress OOM keeps recurring (need to find the large request pattern)

## Rollback

1. **Undo memory change:** Revert resource limits
2. **Undo Ingress deletion:** Reapply from git
3. **Emergency:** Bypass ingress controller, route directly to service NodePort

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| All external traffic down | Platform team + EM | PagerDuty P1 | Immediate |
| Cannot fix config error | Platform team | #platform-support | 5 min |
| Ingress keeps crashing | Platform + security (attack?) | #incident-response | 10 min |

## Notes

- **Ingress is a single point of failure for external traffic.** Run multiple replicas with PDB.
- **Large request headers** can OOM nginx. See [[INC-045-nginx-ingress-oom-large-headers]].
- **Config reload failures** are non-disruptive — NGINX keeps serving with the last good config. But new routes won't work.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Deploy an Ingress with invalid config in staging, verify error handling.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Platform Team | Initial publication |
