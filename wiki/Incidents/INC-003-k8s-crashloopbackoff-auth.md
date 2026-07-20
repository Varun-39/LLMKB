---
id: INC-003
title: auth-service CrashLoopBackOff — Bad Config Secret
severity: SEV-1
service: auth-service
environment: prod
category: outage
date: 2026-05-22
duration: "21m"
detection_gap: "0m"
tags:
  - incident
  - kubernetes
  - crashloop
  - critical
  - prod
  - auth
---
code me give tit in the 
## Summary

All auth-service pods entered CrashLoopBackOff in production at 09:44 UTC on 2026-05-22 following a Kubernetes Secret update during routine credential rotation. The new secret contained a base64-encoding error that prevented startup. Login was fully unavailable for 21 minutes until the secret was corrected.

## Symptoms

- PagerDuty: `AuthService-CrashLoopBackOff` fired at 09:44 UTC
- 100% of login attempts returning HTTP 503
- api-gateway returning 401s for all authenticated endpoints (downstream)
- Pod restart count reached 5 within 4 minutes
- Startup log: `Fatal: could not decode JWT_SIGNING_KEY — illegal base64 character`

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | All users attempting login (~6,200 active sessions disrupted) |
| Services degraded | auth-service (down), api-gateway (auth-dependent endpoints unavailable) |
| Revenue impact | N/A — no transaction pathway affected |
| Duration | 09:44 → 10:05 UTC (21 min) |
| Data loss | None |
| SLA breach | Yes — enterprise SLA (99.9% uptime) breached |
| Customer comms | Status page updated at 09:50 UTC |

## Timeline

| Time (UTC) | Event                                                      |
| ---------- | ---------------------------------------------------------- |
| 09:38      | Credential rotation script executed against prod namespace |
| 09:44      | First pod crash; alert fired immediately                   |
| 09:44      | On-call acknowledged (Sara Ndiaye)                         |
| 09:48      | Root cause identified — corrupt base64 in secret           |
| 10:01      | Corrected secret patched, rollout restart triggered        |
| 10:05      | All pods healthy, login restored                           |
| 10:05      | Incident closed                                            |

## Diagnosis

1. Confirmed CrashLoopBackOff and high restart count
   ```bash
   kubectl get pods -n auth -l app=auth-service
   # auth-service-5c8b4-xr91  0/1  CrashLoopBackOff  5  6m
   ```

2. Pulled startup logs from crashed pod — identified encoding error
   ```bash
   kubectl logs auth-service-5c8b4-xr91 -n auth --previous
   # Fatal: could not decode JWT_SIGNING_KEY — illegal base64 character 0x3d at pos 43
   ```

3. Inspected the secret value — confirmed corrupt encoding
   ```bash
   kubectl get secret auth-jwt-secret -n auth -o jsonpath='{.data.JWT_SIGNING_KEY}' | base64 -d
   # base64: invalid input — confirmed corrupt encoding
   ```

4. Compared against staging secret — staging valid; prod had a stray newline injected during rotation
   ```bash
   diff <(kubectl get secret auth-jwt-secret -n auth -o jsonpath='{.data.JWT_SIGNING_KEY}') \
        <(kubectl get secret auth-jwt-secret -n auth-staging -o jsonpath='{.data.JWT_SIGNING_KEY}')
   ```

## Resolution

1. **Mitigate:** Corrected the secret — re-encoded key without trailing newline
   ```bash
   echo -n "<valid-jwt-key>" | base64
   kubectl patch secret auth-jwt-secret -n auth \
     --type='json' -p='[{"op":"replace","path":"/data/JWT_SIGNING_KEY","value":"<corrected-b64>"}]'
   ```

2. **Fix:** Restarted deployment to pick up corrected secret
   ```bash
   kubectl rollout restart deployment/auth-service -n auth
   kubectl rollout status deployment/auth-service -n auth --timeout=120s
   ```

3. **Verify:** Validated login flow end-to-end
   ```bash
   curl -s -X POST https://auth.internal/login \
     -d '{"user":"smoketest@internal","pass":"<redacted>"}' | jq .status
   # "success"
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Auth down >10 min | Escalate to senior on-call + EM | PagerDuty |
| Secret rotation suspected as root cause | Engage secrets management team | #infra-secrets |
| SLA breach imminent (>15 min outage) | Notify customer success for enterprise accounts | #customer-comms |

## Post-Incident Review

**What went well:**
- Alert fired within 30 seconds of first crash
- Root cause identified in logs within 4 minutes of alert

**What needs improvement:**
- No validation step in the secret rotation runbook
- Manual base64 encoding is error-prone; no tooling enforcing correct encoding

**Contributing factors (beyond root cause):**
- Rotation script lacked a post-write validation step
- No dry-run mode available for secret rotation in prod

**Action items:**

| Action                                                             | Owner         | Due Date   | Status |
| ------------------------------------------------------------------ | ------------- | ---------- | ------ |
| Add base64 validation step to credential rotation runbook          | Sara Ndiaye   | 2026-06-05 | Open   |
| Implement pre-rotation secret validation script in CI              | Platform team | 2026-06-12 | Open   |
| Add Secret change audit log alerts to catch prod/staging confusion | SRE team      | 2026-06-12 | Open   |

## Links

- Runbooks: [[RB-007-pod-crash-investigation]]
- Related incidents: N/A
- PR/commit: N/A
- Post-mortem doc: N/A
