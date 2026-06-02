---
id: INC-003
title: auth-service CrashLoopBackOff — Bad Config Secret
severity: SEV-1
service: auth-service
environment: prod
category: outage
status: resolved
owner: Sara Ndiaye
assigned-to: Sara Ndiaye
date: 2026-05-22
duration: 21 minutes
created: 2026-05-22
updated: 2026-05-22
tags:
  - incident
  - kubernetes
  - crashloop
  - config
  - critical
  - prod
  - auth
related_runbooks:
  - "[[RB-006-pod-crash]]"
related_incidents: []
---

# INC-003 — auth-service CrashLoopBackOff: Bad Config Secret

## Summary

All auth-service pods entered CrashLoopBackOff in production at 09:44 UTC on 2026-05-22, immediately following a Kubernetes Secret update pushed during routine credential rotation. The service failed on startup because the new secret contained a base64-encoding error. Login was fully unavailable for 21 minutes until the secret was corrected and pods restarted cleanly.

## Symptoms

- PagerDuty: `AuthService-CrashLoopBackOff` at 09:44 UTC
- 100% of login attempts returning HTTP 503
- Downstream: api-gateway returning 401s for all authenticated endpoints
- Pod restart count reached 5 within 4 minutes
- Startup log: `Fatal: could not decode JWT_SIGNING_KEY — illegal base64 character`

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All users attempting login (~6,200 active sessions disrupted) |
| Services degraded | auth-service (down), api-gateway (auth-dependent endpoints unavailable) |
| Revenue impact | N/A — no transaction pathway, but SLA breach for enterprise customers |
| Duration | 09:44 → 10:05 UTC (21 min) |
| Data loss | None |

## Possible Causes

1. **Malformed base64 in Secret** — encoding error during manual secret creation
2. **Wrong key referenced** — Secret updated for staging, accidentally applied to prod namespace
3. **Secret version mismatch** — application expecting v2 key format, secret still in v1 format
4. **Permissions issue** — pod unable to read mounted secret volume (filesystem permissions)

## Troubleshooting Steps

1. Confirmed CrashLoopBackOff and high restart count
   ```bash
   kubectl get pods -n auth -l app=auth-service
   # auth-service-5c8b4-xr91  0/1  CrashLoopBackOff  5  6m
   ```

2. Pulled startup logs from crashed pod
   ```bash
   kubectl logs auth-service-5c8b4-xr91 -n auth --previous
   # Fatal: could not decode JWT_SIGNING_KEY — illegal base64 character 0x3d at pos 43
   ```

3. Inspected the secret value
   ```bash
   kubectl get secret auth-jwt-secret -n auth -o jsonpath='{.data.JWT_SIGNING_KEY}' | base64 -d
   # base64: invalid input — confirmed corrupt encoding
   ```

4. Compared against staging secret — staging secret was valid; prod had a stray newline injected during rotation

5. Verified pod had correct secret mount path
   ```bash
   kubectl describe pod auth-service-5c8b4-xr91 -n auth | grep -A5 "Mounts"
   ```

## Resolution

1. Corrected the secret — re-encoded key without trailing newline
   ```bash
   echo -n "<valid-jwt-key>" | base64
   kubectl patch secret auth-jwt-secret -n auth \
     --type='json' -p='[{"op":"replace","path":"/data/JWT_SIGNING_KEY","value":"<corrected-b64>"}]'
   ```

2. Restarted deployment to pick up corrected secret
   ```bash
   kubectl rollout restart deployment/auth-service -n auth
   kubectl rollout status deployment/auth-service -n auth --timeout=120s
   ```

3. Validated login flow end-to-end
   ```bash
   curl -s -X POST https://auth.internal/login \
     -d '{"user":"smoketest@internal","pass":"<redacted>"}' | jq .status
   # "success"
   ```

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Auth down >10 min | Escalate to senior on-call + EM | PagerDuty |
| Secret rotation suspected as root cause | Engage secrets management team | #infra-secrets |
| SLA breach imminent (>15 min outage) | Notify customer success for enterprise accounts | #customer-comms |

## Post-Incident Notes

**Went well:**
- Alert fired within 30 seconds of first crash
- Root cause identified in logs within 4 min of alert

**Improve:**
- No validation step in the secret rotation runbook
- Manual base64 encoding is error-prone; no tooling enforcing correct encoding

**Action items:**
- [x] Corrected secret and restored service
- [ ] Add base64 validation step to credential rotation runbook
- [ ] Implement pre-rotation secret validation script in CI
- [ ] Add Secret change audit log alerts to catch prod/staging confusion

## Related Runbooks

- [[RB-006-pod-crash]]
