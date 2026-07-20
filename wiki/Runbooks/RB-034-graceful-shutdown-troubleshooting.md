---
id: RB-034
title: Graceful Shutdown and Request Draining Troubleshooting
service: "*"
related_services:
  - api-gateway
  - payment-service
  - ingress-controller
severity: SEV-2
environment: prod
category: deployment
risk_level: medium
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - graceful-shutdown
  - draining
  - deployment
  - kubernetes
  - prod
related_incidents:
  - "[[INC-048-aws-alb-target-deregistration-delay]]"
  - "[[INC-010-release-failed-canary-api]]"
related_runbooks:
  - "[[RB-006-failed-deployment-rollback]]"
  - "[[RB-026-ingress-controller-troubleshooting]]"
related_guardrails: []
---

## Purpose

Diagnose and fix request drops during deployments caused by improper graceful shutdown configuration, missing preStop hooks, or load balancer deregistration timing issues.

**Desired outcome:** Zero dropped requests during rolling deployments, clean connection draining.

## Success Criteria

- Zero HTTP 502/503 errors during deployment
- In-flight requests complete before pod terminates
- Load balancer stops routing before pod shuts down
- Connection drain time sufficient for longest request

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any service experiencing request drops during deploys |
| Related services | api-gateway, payment-service, ingress-controller |
| Environments | prod, staging |
| Use when | 502/503 errors correlating with deployment rollouts |
| Do NOT use when | Errors exist outside of deployment windows (service issue) |
| Risk level | Medium |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] Access to deployment configuration (pod spec)
- [ ] Load balancer configuration access
- [ ] Knowledge of service's longest request duration

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Pod spec and deployment inspection | Cluster admin |
| Load balancer config | Deregistration delay settings | Admin |
| Access logs | Error correlation with pod termination | Read access |

## Trigger

- 502/503 errors correlating with deployment timestamps
- Clients receiving "connection reset" during deployments
- Monitoring showing brief error spikes during every rollout

## Investigation

1. **Check pod termination configuration**
   ```bash
   kubectl get deployment <name> -n <namespace> -o yaml | grep -A10 "lifecycle\|terminationGrace"
   # What to look for: preStop hook, terminationGracePeriodSeconds
   ```

2. **Check load balancer deregistration delay**
   ```bash
   # ALB:
   aws elbv2 describe-target-group-attributes --target-group-arn <arn> | grep deregistration
   # What to look for: deregistration_delay should be < terminationGracePeriodSeconds
   ```

3. **Correlate errors with pod termination**
   ```bash
   kubectl get events -n <namespace> --sort-by='.lastTimestamp' | grep Killing
   # Compare timestamps with error spikes in access logs
   ```

## Mitigation

### Fix graceful shutdown timing:

```bash
# 1. Add preStop hook (gives LB time to deregister):
kubectl patch deployment <name> -n <namespace> --type='json' \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/lifecycle","value":{"preStop":{"exec":{"command":["sh","-c","sleep 15"]}}}}]'

# 2. Ensure terminationGracePeriodSeconds > preStop + drain time:
kubectl patch deployment <name> -n <namespace> \
  -p='{"spec":{"template":{"spec":{"terminationGracePeriodSeconds":45}}}}'

# 3. Set deregistration delay < terminationGracePeriodSeconds:
aws elbv2 modify-target-group-attributes --target-group-arn <arn> \
  --attributes Key=deregistration_delay.timeout_seconds,Value=20
```

**Timing formula:** `terminationGracePeriodSeconds` > `preStop sleep` + `deregistration_delay` + `longest request duration`

## Verification

- [ ] Next deployment shows 0 HTTP 502/503 errors
- [ ] Access logs confirm clean request completion during rollout
- [ ] No "connection reset" errors from clients

```bash
# Deploy and watch errors:
kubectl rollout restart deployment/<name> -n <namespace>
# While rolling, check for errors:
curl -s -o /dev/null -w "%{http_code}" https://<service>/health
# Should always be 200 during rollout
```

## Notes

- **The order is:** LB stops sending new traffic → preStop sleep → SIGTERM → app drains → SIGKILL (after grace period).
- **Default terminationGracePeriodSeconds is 30s.** Often too short for payment or long-polling services.
- **ALB default deregistration delay is 300s.** Almost always wrong — set to 15-20s for K8s workloads. See [[INC-048-aws-alb-target-deregistration-delay]].
- **readinessProbe** should fail immediately on SIGTERM to tell the service mesh/LB to stop routing.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Deploy in staging while running continuous requests, verify zero errors.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
