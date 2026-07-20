---
id: RB-<NNN>
title: <short-descriptive-title>
service: <service-name>
related_services:
  - <dependent-service>
  - <upstream-or-downstream-service>
severity: <SEV-1|SEV-2|SEV-3|SEV-4>
environment: <prod|staging|dev>
category: <resource-exhaustion|connectivity|deployment|security|performance>
risk_level: <low|medium|high>
estimated_duration: <e.g. "15m" or "30m">
approval_required: <yes|no>
approver_role: <role or team required to approve, if applicable>
tags:
  - runbook
  - <technology>
  - <issue-type>
  - <severity-tag>
  - <environment>
  - <service-area>
---
## Purpose

<One sentence: what failure does this runbook address and for which service.>

**Desired outcome:** <What "success" looks like after executing this runbook.>

## Success Criteria

Before closing the incident or declaring the runbook complete, ALL of the following must be true:

- <Primary metric returned to normal — e.g., error rate < 1%>
- <Resource usage within safe bounds — e.g., CPU < 70%, memory < 80%>
- <No active alerts for this service for at least 15 minutes>
- <Health endpoint returning 200>
- <Downstream services unaffected and operating normally>

## Scope   
#Where should this runbook be used?

| Attribute | Value |
|-----------|-------|
| Service | <service-name> |
| Related services | <list of dependent or upstream/downstream services> |
| Environments | <prod, staging> |
| Use when | <trigger condition — alert name, symptom, metric threshold> |
| Do NOT use when | <exclusion — when this runbook is the wrong choice> |
| Risk level | <low / medium / high> |
| Estimated duration | <e.g. 10–15 minutes> |
| Approval required | <yes / no — if yes, who approves> |

## Prerequisites

- [ ] `kubectl` access to `<namespace>` confirmed
- [ ] VPN / network access to target environment
- [ ] Monitoring dashboard accessible
- [ ] On-call role confirmed in PagerDuty/Opsgenie
- [ ] Approval obtained (if `approval_required: yes`) — documented in #change-management
- [ ] <Additional access or tools required>

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Pod/deployment operations | Cluster admin |
| Grafana | Metric verification | Read access |
| `psql` / DB client | Database diagnostics | Superuser (for diagnostics) |
| <additional> | <purpose> | <level> |

## Trigger
<where should i use this runbook >
- Alert: `<alert-name>` fires in monitoring
- Symptom: <observable behavior that should make you reach for this runbook>
- Metric: <specific threshold — e.g., memory > 90% for 5 min>

## Triage

<Quick checks to confirm this is the right runbook before committing to full execution, Am I looking at the right problem?>

1. Confirm the alert is genuine
   ```bash
   <verification command>
   ```
2. Assess blast radius — isolated vs. widespread
   ```bash
   <command>
   ```
3. Wrong symptoms? → Try [[alternative-runbook]]

## Investigation

<Deeper diagnosis once triage confirms this is the right runbook. , How to find the root cause.>

1. **Check primary indicator**
   ```bash
   <command>
   # What to look for: <expected vs. abnormal output>
   ```
2. **Check secondary indicator**
   ```bash
   <command>
   ```
3. **Correlate with recent changes**
   ```bash
   <command>
   ```
4. **Decision point:**
   - IF <condition A> → proceed to Mitigation Option A
   - IF <condition B> → proceed to Mitigation Option B
   - IF unclear → escalate (see Escalation section)

## Mitigation
<How do I stop the damage?, migitation means reducing inmapct for now not the final fix>

### Option A: <primary-fix-name>

```bash
<command>
```

### Option B: <secondary-fix-name>

```bash
<command>
```

### Option C: <rollback-or-scale-fix>

```bash
<command>
```

**After mitigation:** Monitor for 10–15 minutes before declaring resolved.

## Verification
<Did the mitigation work?>

- [ ] Service health endpoint returning 200
- [ ] Error rate returned to baseline (< X%)
- [ ] No new alerts in 15 minutes
- [ ] <Metric> stable below threshold

```bash
<health check command>
# Expected: <healthy output>
```

## Failure Signals

If the mitigation did NOT work, you will observe one or more of the following:

- <Error rate continues to rise or does not decrease within 5 minutes>
- <Resource usage (CPU/memory/disk) continues climbing>
- <Health endpoint still returning non-200 status>
- <New alerts firing for the same or related services>
- <Downstream services beginning to degrade>

**If any failure signal is present after mitigation:** Do NOT repeat the same step. Proceed to Rollback or Escalation immediately.

## Rollback

<If mitigation made things worse, how to undo each option. also Recovery from failed recovery.>

1. **Undo Option A:**
   ```bash
   <command>
   ```
2. **Undo Option B:**
   ```bash
   <command>
   ```
3. Notify #incident-response: "Rollback executed — escalating."

## Escalation
<When should I ask for help?, to whom>
| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| No fix in 30 min | Senior on-call | PagerDuty | 5 min response |
| Customer-facing SEV-1 | EM + IC | #incident-response | Immediate |
| Infrastructure-level failure | Platform/SRE | #platform-support | 10 min |
| Security concern | SecOps | #security-urgent | Immediate |
| Guardrail violation detected | See related guardrail | #change-management | Before proceeding |

## Notes

- <Common pitfall or environment-specific quirk>
- <Edge case where this runbook behaves differently>
- <Historical context from past incidents for eg. this issue happens after quaterly maintainance>
- See also: [[INC-xxx-title]], [[RB-xxx-title]]

## Maintenance
<Is this runbook still valid?>
- **Last tested:** <YYYY-MM-DD>
- **Review cycle:** Quarterly
- **Next review:** <YYYY-MM-DD>
- **Test method:** <How to validate this runbook still works — dry run, chaos test, etc.>

## last Updated
<Who changed what?>

| Date | Author | Change |
|------|--------|--------|
| <YYYY-MM-DD> | <name> | Initial publication |
| <YYYY-MM-DD> | <name> | <what changed> |
