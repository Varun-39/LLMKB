---
id: INC-019
title: Broken Feature Flag — auth-service New Login Flow Enabled in Prod
severity: SEV-1
service: auth-service
environment: prod
category: deployment-failure
status: resolved
owner: Sara Ndiaye
assigned-to: Sara Ndiaye
date: 2026-02-27
duration: 18 minutes
created: 2026-02-27
updated: 2026-02-27
tags:
  - incident
  - deployment
  - feature-flag
  - auth
  - critical
  - prod
  - auth
related_runbooks:
  - "[[RB-005-failed-deployment]]"
related_incidents:
  - "[[INC-003-k8s-crashloopbackoff-auth]]"
  - "[[INC-011-rollback-failed-frontend]]"
---

# INC-019 — Broken Feature Flag: auth-service New Login Flow Enabled in Prod

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

## Possible Causes

1. **Feature flag enabled prematurely in prod** — `enable_mfa_v2` toggled by developer for manual testing on prod, not staging
2. **Incomplete implementation** — SSO code path in `MfaV2Handler` not implemented, `ssoContext` never populated
3. **No flag change alerting** — flag state changes not logged to a monitored audit stream
4. **Missing nil/null guard** — `ssoContext` used without null check despite being potentially absent

## Troubleshooting Steps

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

1. Disabled `enable_mfa_v2` flag in LaunchDarkly immediately
   - Flag change propagated to auth-service within 30 seconds (polling interval)

2. Confirmed SSO login success rate recovered to 99.9% within 60 seconds

3. No pod restart required — flag is polled dynamically without code reload

4. Notified affected enterprise accounts via customer success team

## Escalation Criteria

| Trigger | Action | Channel |
|---------|--------|---------|
| Login failure rate >5% for >5 min | Page on-call SRE + EM | PagerDuty |
| Enterprise SLA accounts impacted | Notify customer success immediately | #customer-comms |
| Flag cannot be disabled (LaunchDarkly outage) | Roll back to previous auth-service image | #incident-response |

## Post-Incident Notes

**Went well:**
- Flag disable resolved the incident instantly with no deployment needed
- SSO vs. password split in metrics helped isolate the affected code path in minutes

**Improve:**
- No approval gate for enabling flags in prod — any developer could flip a prod flag
- Feature flag changes not alerted on or audited in real-time
- Incomplete code path shipped behind a flag with no guard for the unimplemented branch

**Action items:**
- [x] Disabled flag, SSO logins restored
- [ ] Add approval workflow for enabling feature flags in prod (require 2 approvers)
- [ ] Send flag change events to Datadog as custom events for correlation
- [ ] Add null guard to all new flag-gated code paths before merging
- [ ] Block prod flag changes from developer accounts during business hours without change ticket

## Related Runbooks

- [[RB-005-failed-deployment]]
