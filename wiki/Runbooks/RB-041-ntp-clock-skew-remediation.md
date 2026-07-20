---
id: RB-041
title: NTP Clock Skew Detection and Remediation
service: general
related_services:
  - auth-service
  - payment-service
severity: SEV-2
environment: prod
category: security
risk_level: medium
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - ntp
  - clock-skew
  - chrony
  - jwt
  - tls
  - auth
  - prod
---

## Purpose

Detect and correct NTP clock drift on production nodes that causes JWT validation failures, TLS certificate errors, or time-sensitive authentication issues.

**Desired outcome:** All nodes synchronised to NTP with offset < 1 second, auth/TLS errors resolved.

## Success Criteria

- All nodes: `chronyc tracking` shows offset < 0.1 seconds
- chrony service `active (running)` on all nodes
- JWT validation errors / TLS errors resolved
- Auth-service error rate back to baseline

## Scope

| Attribute | Value |
|-----------|-------|
| Service | All nodes, especially auth-service nodes |
| Environments | prod |
| Use when | JWT `not yet valid` errors, TLS validation failures, or clock-skew alert fires |
| Do NOT use when | TLS cert is actually expired (use RB-011 instead) |
| Risk level | Medium — forcing clock step can disrupt time-ordering of logs |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] SSH access to affected nodes
- [ ] `kubectl` access to affected services
- [ ] Know which nodes host the failing pods

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `ssh` | Node access | Node admin |
| `chronyc` | NTP status and correction | Root |
| `kubectl` | Identify affected pods and nodes | Read access |

## Trigger

- Alert: `node_clock_skew_seconds > 10`
- Log pattern: `JWT: token is not valid yet`, `TLS: certificate not yet valid`, `clock skew too great`
- Symptom: Auth errors affecting only some pods (not all — only pods on drifted nodes)

## Triage

1. Confirm errors are node-specific (not all pods):
   ```bash
   kubectl logs -n auth deploy/auth-service | grep "not valid yet" | grep -oP 'node=\S+' | sort | uniq -c
   # If concentrated on 1-2 nodes → clock skew, not a config issue
   ```
2. Check clock on the suspected node:
   ```bash
   ssh <node> date && date -u
   # Compare output — if > 10 seconds off from your terminal's clock, confirmed
   ```
3. Check chrony status:
   ```bash
   ssh <node> systemctl status chronyd
   # If "inactive" or "failed" → chrony is not running
   ```

## Investigation

1. **Check exact offset on all nodes**
   ```bash
   for node in $(kubectl get nodes -o name | cut -d/ -f2); do
     echo "$node: $(ssh $node chronyc tracking | grep 'System time')"
   done
   # What to look for: any offset > 5s is worth correcting
   ```
2. **Check why chrony stopped (if applicable)**
   ```bash
   ssh <node> journalctl -u chronyd --since "1 hour ago" | tail -30
   # Look for: killed during update, masked, dependency failure
   ```
3. **Decision point:**
   - IF chrony stopped → Option A (restart)
   - IF chrony running but large offset → Option B (force step)
   - IF NTP server unreachable → Option C (check network)

## Mitigation

### Option A: Restart chrony (if stopped)

```bash
ssh <node> systemctl enable --now chronyd
ssh <node> systemctl status chronyd
# Verify: active (running)
```

### Option B: Force immediate clock correction (chrony running but drifted)

```bash
ssh <node> chronyc makestep
# This immediately steps the clock rather than slewing slowly
ssh <node> chronyc tracking | grep "System time"
# Expected: < 0.001 seconds fast/slow
```

### Option C: Check NTP server connectivity

```bash
ssh <node> chronyc sources
# Look for: * (synced) or + (combined) symbols
# If all show "?" or "x" → NTP server unreachable
ssh <node> ping ntp.ubuntu.com  # or your internal NTP server
```

**After mitigation:** JWT/TLS errors should clear within 60 seconds of clock correction.

## Verification

- [ ] `chronyc tracking` on affected nodes shows offset < 0.1s
- [ ] JWT validation errors stopped in application logs
- [ ] Auth-service error rate back to baseline

```bash
ssh <node> chronyc tracking | grep "System time"
# Expected: System time: 0.000123 seconds fast of NTP time
```

## Failure Signals

- Clock corrected but errors persist (check if app caches JWT claims — may need pod restart)
- chrony restarts but immediately stops (check for masked unit or config error)
- Offset not decreasing after `makestep` (NTP unreachable — escalate)

## Rollback

- Clock correction is not reversible (and shouldn't be — incorrect time is the bug).
- If `makestep` causes log timestamp discontinuity, note the correction time in the incident record.
- If application pods need a restart to clear cached state:
  ```bash
  kubectl rollout restart deployment/auth-service -n auth
  ```

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| NTP server unreachable across multiple nodes | Network/Infrastructure | #platform-support | 10 min |
| Clock skew on control plane nodes (etcd risk) | Platform Lead | PagerDuty | Immediate |
| chrony config corrupted or missing | Infrastructure | #platform-support | 10 min |

## Notes

- Always add `systemctl enable chronyd` to post-kernel-update runbooks.
- Add 5-second `leeway` to JWT validators to tolerate minor drift: minor skew shouldn't cause outages.
- etcd is extremely sensitive to clock skew — control plane node drift > 1s can cause election failures.
- See [[INC-099-jwt-clock-skew-auth-rejection]] and [[INC-063-node-clock-skew-tls-failures]].

## Maintenance

- **Last tested:** 2026-05-16
- **Review cycle:** Quarterly
- **Next review:** 2026-08-16
- **Test method:** Stop chronyd on a staging node, verify alert fires, execute runbook.

## last Updated

| Date | Author | Change |
|------|--------|--------|
| 2026-05-16 | Platform Team | Initial publication |
