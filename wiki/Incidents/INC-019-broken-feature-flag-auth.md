---
id: INC-019
title: Broken Feature Flag — auth-service New Login Flow Enabled in Prod
severity: SEV-1
service: auth-service
environment: prod
category: deployment-failure
date: 2026-02-27
duration: "18m"
detection_gap: "2m"
tags:
  - incident
  - deployment
  - feature-flag
  - auth
  - critical
  - prod
  - auth
error_family: broken-feature-flag
resolution_runbook: RB-006
resolution_outcome: resolved
---

## Summary

At 16:45 UTC on 2026-02-27, a feature flag `enable_mfa_v2` was enabled in prod by a developer testing a new MFA flow before it was ready for release. The new flow contained an unfinished code path that threw `NullPointerException` on every login attempt using SSO. 100% of SSO-based logins failed for 18 minutes until the flag was disabled. Password-based logins were unaffected.

## Symptoms

- PagerDuty: `AuthService-LoginFailureRateHigh` at 16:47 UTC
- auth-service logs: `NullPointerException at MfaV2Handler.java:114 — ssoContext was null`
- SSO login failure rate: 100% (all SSO providers: Google, GitHub, Okta)
- Password-based login success rate: unaffected at 99.8%
- Sentry: `NullPointerException` spike from 0 to 450/min at 16:45 UTC
- Affected users: all enterprise customers using SSO

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~1,800 enterprise users using SSO |
| Services degraded | auth-service (SSO login path fully broken) |
| Revenue impact | Potential SLA breach for 6 enterprise accounts |
| Duration | 16:45 → 17:03 UTC (18 min) |
| Data loss | None |
| SLA breach | Yes — enterprise SLA (99.9% uptime) breached for SSO login path |
| Customer comms | Enterprise accounts notified via customer success team |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 16:44 | Developer enabled `enable_mfa_v2` flag in prod via LaunchDarkly |
| 16:45 | First SSO login failures began |
| 16:47 | Alert fired: `AuthService-LoginFailureRateHigh` |
| 16:48 | On-call acknowledged (Sara Ndiaye) |
| 16:52 | Feature flag identified as cause via logs |
| 16:54 | `enable_mfa_v2` flag disabled in LaunchDarkly |
| 16:55 | SSO login success rate recovered to 99.9% |
| 17:03 | Enterprise accounts notified, incident closed |

## Diagnosis

1. Confirmed SSO failure rate and error pattern
   ```bash
   kubectl logs -l app=auth-service -n auth --tail=100 \
     | grep "NullPointerException" | head -10
   # NullPointerException at MfaV2Handler.java:114
   # ssoContext = null — all SSO login attempts
   ```

2. Determined which code path was activated
   ```bash
   kubectl logs -l app=auth-service -n auth --tail=50 \
     | grep "enable_mfa_v2"
   # [INFO] Feature flag 'enable_mfa_v2' is ENABLED — routing to MfaV2Handler
   ```

3. Checked feature flag state in LaunchDarkly console
   - `enable_mfa_v2`: ON for 100% of users in prod environment
   - Changed by: `dev-user@company.com` at 16:44:57 UTC

4. Confirmed password login path was unaffected (does not call MfaV2Handler)

## Resolution

1. **Mitigate:** Disabled `enable_mfa_v2` flag in LaunchDarkly immediately
   ```bash
   # Flag change propagated to auth-service within 30 seconds (polling interval)
   ```

2. **Fix:** No code deployment needed — flag is polled dynamically without code reload

3. **Verify:** Confirmed SSO login success rate recovered to 99.9% within 60 seconds
   ```bash
   # Grafana: SSO login success rate 99.9% at 16:55 UTC
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| Login failure rate >5% for >5 min | Page on-call SRE + EM | PagerDuty |
| Enterprise SLA accounts impacted | Notify customer success immediately | #customer-comms |
| Flag cannot be disabled (LaunchDarkly outage) | Roll back to previous auth-service image | #incident-response |

## Post-Incident Review

**What went well:**
- Flag disable resolved the incident instantly with no deployment needed
- SSO vs. password split in metrics helped isolate the affected code path in minutes

**What needs improvement:**
- No approval gate for enabling flags in prod — any developer could flip a prod flag
- Feature flag changes not alerted on or audited in real-time
- Incomplete code path shipped behind a flag with no guard for the unimplemented branch

**Contributing factors (beyond root cause):**
- Developer testing in prod instead of staging (no environment distinction in flag UI)
- `MfaV2Handler.java` SSO code path not implemented, `ssoContext` never populated
- No null guard on `ssoContext` despite being potentially absent

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Disable flag, restore SSO logins | Sara Ndiaye | 2026-02-27 | Done |
| Add approval workflow for enabling feature flags in prod (require 2 approvers) | Platform team | 2026-03-13 | Open |
| Send flag change events to Datadog as custom events for correlation | SRE team | 2026-03-13 | Open |
| Add null guard to all new flag-gated code paths before merging | Platform team | 2026-03-13 | Open |
| Block prod flag changes from developer accounts during business hours without change ticket | Platform team | 2026-03-20 | Open |

## Links

- Runbooks: [[RB-006-failed-deployment-rollback]]
- Related incidents: [[INC-003-k8s-crashloopbackoff-auth]], [[INC-011-rollback-failed-frontend]]
- PR/commit: N/A
- Post-mortem doc: N/A
