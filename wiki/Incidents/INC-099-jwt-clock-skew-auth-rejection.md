---
id: INC-099
title: JWT Validation Failures Due to NTP Clock Skew on Auth Nodes
severity: SEV-2
service: auth-service
environment: prod
category: degradation
date: 2026-05-09
duration: "28m"
tags:
  - incident
  - jwt
  - clock-skew
  - ntp
  - auth-service
  - prod
error_family: unknown
resolution_runbook: RB-011
resolution_outcome: resolved
---

## Summary

Two auth-service nodes drifted 95 seconds ahead of true UTC after the NTP daemon (chrony) was accidentally disabled during a kernel update. JWT tokens issued by these nodes had `iat` (issued-at) 95 seconds in the future from the perspective of validating services, which were correctly-clocked. All tokens issued by the drifted nodes were rejected as "not yet valid", locking out ~3,800 users until the clock was corrected.

## Symptoms

- auth-service: `JWT validation failed: token is not valid yet (iat in future)`
- Users: intermittent authentication failures (affected ~50% of login attempts — only nodes with drifted clock)
- NTP offset on auth-node-03, auth-node-04: `+95s` (chrony status: stopped)
- auth-service error rate: 48% (only requests hitting drifted nodes)

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~3,800 users unable to authenticate |
| Services degraded | auth-service (50% of nodes issuing invalid JWTs) |
| Revenue impact | ~$4.1K (abandoned sessions) |
| Duration | 10:15 → 10:43 UTC (28 min) |
| Data loss | None |
| SLA breach | Yes — auth availability SLA breached |
| Customer comms | Status page: "Users may experience login issues" |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 09:45 | Kernel update applied to auth-node-03 and auth-node-04 |
| 09:50 | chrony disabled during update; not re-enabled |
| 10:00 | Clocks begin drifting |
| 10:15 | JWT validation error rate exceeds 5%; alert fires |
| 10:20 | On-call begins investigation |
| 10:30 | Clock skew identified |
| 10:35 | chrony restarted; clock slewed back to UTC |
| 10:43 | All JWT validations passing |

## Diagnosis

1. Checked error pattern — not all requests failing (only ~50%):
   ```bash
   kubectl logs -n auth deploy/auth-service | grep "not valid yet" | awk '{print $NF}' | sort | uniq -c
   # 1921 auth-node-03
   # 1882 auth-node-04
   ```
2. Checked NTP status on affected nodes:
   ```bash
   ssh auth-node-03 chronyc tracking
   # System time: 95.3 seconds fast of NTP time
   ssh auth-node-03 systemctl status chronyd
   # inactive (dead)
   ```
3. Confirmed chrony stopped after kernel update (unit masked):
   ```bash
   ssh auth-node-03 systemctl is-enabled chronyd
   # disabled
   ```

## Resolution

1. **Re-enabled and started chrony** on both nodes:
   ```bash
   ssh auth-node-03 systemctl enable --now chronyd
   ssh auth-node-04 systemctl enable --now chronyd
   ```
2. **Force stepped clock** back to NTP time immediately (rather than slewing slowly):
   ```bash
   ssh auth-node-03 chronyc makestep
   ssh auth-node-04 chronyc makestep
   ```
3. JWT validations immediately passed once clock corrected
4. **Verify:**
   ```bash
   ssh auth-node-03 chronyc tracking | grep "System time"
   # System time: 0.0001 seconds fast of NTP time
   ```

## Post-Incident Review

**What went well:**
- Node-specific error pattern in logs pinpointed affected nodes quickly

**What needs improvement:**
- Kernel update procedure didn't include "verify chrony running" post-check
- No alert on node clock skew > 5 seconds

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add NTP sync check to post-kernel-update runbook | Platform | 2026-05-16 | Open |
| Add node clock skew alert (threshold: > 10s vs NTP) | Observability | 2026-05-16 | Open |
| Add JWT `iat` leeway of 5 seconds in validators to tolerate minor skew | Backend | 2026-05-16 | Open |

## Links

- Runbooks: [[RB-011-tls-certificate-renewal]]
- Related incidents: [[INC-063-node-clock-skew-tls-failures]], [[INC-056-oauth-token-signing-key-rotation-failure]]
