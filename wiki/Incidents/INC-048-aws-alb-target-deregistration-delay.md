---
id: INC-048
title: ALB Target Deregistration Delay Causing 502s During Deployments
severity: SEV-3
service: api-gateway
environment: prod
category: deployment-failure
date: 2026-04-28
duration: "8m"
tags:
  - incident
  - aws
  - alb
  - deployment
  - load-balancer
  - moderate
  - prod
error_family: unknown
resolution_runbook: RB-006
resolution_outcome: resolved
---

## Summary

During every deployment of api-gateway, users experienced 5-10 seconds of HTTP 502 errors. Root cause: the ALB target deregistration delay was set to 300 seconds (default), but the pod's `terminationGracePeriodSeconds` was only 30 seconds. Pods terminated before the ALB stopped sending traffic to them, causing 502s on in-flight requests routed to terminated pods.

## Symptoms

- Recurring 502 errors during every api-gateway deployment (8-12 per deploy)
- CloudWatch ALB metrics: `HTTP_502_Count` spike correlating with rollout
- No alerts (brief duration, within error budget)
- User reports: occasional "Something went wrong" during business hours

## Diagnosis

1. Correlated 502 timing with pod termination
   ```bash
   kubectl get events -n api --sort-by='.lastTimestamp' | grep Killing
   # Pod killed at exact same timestamp as 502 spike in ALB logs
   ```

2. Checked deregistration delay
   ```bash
   aws elbv2 describe-target-group-attributes --target-group-arn <arn> | grep deregistration_delay
   # deregistration_delay.timeout_seconds: 300
   ```

3. Pod terminationGracePeriodSeconds: 30 (pod dies 270s before ALB stops routing to it)

## Resolution

1. **Fix:** Set deregistration delay to 20s (less than terminationGracePeriodSeconds)
   ```bash
   aws elbv2 modify-target-group-attributes --target-group-arn <arn> \
     --attributes Key=deregistration_delay.timeout_seconds,Value=20
   ```

2. Added `preStop` lifecycle hook with 15s sleep to allow in-flight requests to complete

3. **Verify:** Next deployment: 0 HTTP 502 errors

## Post-Incident Review

- Default ALB deregistration delay (300s) is almost always wrong for K8s deployments
- Standardized all target groups: deregistration delay = terminationGracePeriodSeconds - 10
- Added preStop hook to all deployments receiving ALB traffic

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]]
- Related incidents: [[INC-010-release-failed-canary-api]]
