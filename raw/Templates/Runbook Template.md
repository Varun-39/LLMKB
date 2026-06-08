---
id: RB-<NNN>
title: <short-descriptive-title>
service: <service-name>
severity: <SEV-1|SEV-2|SEV-3|SEV-4>
environment: <prod|staging|dev>
category: <resource-exhaustion|connectivity|deployment|security|performance>
status: <active|deprecated|under-review>
owner: <owner-name>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
tags:
  - runbook
  - <technology>
  - <issue-type>
  - <severity-tag>
  - <environment>
  - <service-area>
related_incidents:
  - "[[INC-xxx-title]]"
related_runbooks:
  - "[[RB-xxx-title]]"
---

## Purpose

<One sentence: what failure does this runbook address and for which service.>

**Desired outcome:** <What "success" looks like after executing this runbook.>

## Scope

| Attribute | Value |
|-----------|-------|
| **Service** | <service-name> |
| **Environments** | <prod, staging> |
| **Use when** | <trigger condition — alert name, symptom, metric threshold> |
| **Do NOT use when** | <exclusion — when this runbook is the wrong choice> |

## Prerequisites

- [ ] `kubectl` access to `<namespace>` confirmed
- [ ] VPN / network access to target environment
- [ ] Monitoring dashboard accessible
- [ ] On-call role confirmed in PagerDuty/Opsgenie
- [ ] <Additional access or tools required>

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Pod/deployment operations | Cluster admin |
| Grafana | Metric verification | Read access |
| `psql` / DB client | Database diagnostics | Superuser (for diagnostics) |
| <additional> | <purpose> | <level> |

## Trigger

- Alert: `<alert-name>` fires in monitoring
- Symptom: <observable behavior that should make you reach for this runbook>
- Metric: <specific threshold — e.g., memory > 90% for 5 min>

## Triage

<Quick checks to confirm this is the right runbook before committing to full execution.>

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

<Deeper diagnosis once triage confirms this is the right runbook.>

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

- [ ] Service health endpoint returning 200
- [ ] Error rate returned to baseline (< X%)
- [ ] No new alerts in 15 minutes
- [ ] <Metric> stable below threshold

```bash
<health check command>
# Expected: <healthy output>
```

## Rollback

<If mitigation made things worse, how to undo each option.>

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

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| No fix in 30 min | Senior on-call | PagerDuty | 5 min response |
| Customer-facing SEV-1 | EM + IC | #incident-response | Immediate |
| Infrastructure-level failure | Platform/SRE | #platform-support | 10 min |
| Security concern | SecOps | #security-urgent | Immediate |

## Notes / Gotchas

- <Common pitfall or environment-specific quirk>
- <Edge case where this runbook behaves differently>
- <Historical context from past incidents>
- See also: [[INC-xxx-title]], [[RB-xxx-title]]

## Maintenance

- **Last tested:** <YYYY-MM-DD>
- **Review cycle:** Quarterly
- **Next review:** <YYYY-MM-DD>
- **Test method:** <How to validate this runbook still works — dry run, chaos test, etc.>

## Revision History

| Date | Author | Change |
|------|--------|--------|
| <YYYY-MM-DD> | <name> | Initial publication |
| <YYYY-MM-DD> | <name> | <what changed> |
