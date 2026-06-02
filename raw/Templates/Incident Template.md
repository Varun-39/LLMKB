---
id: INC-<NNN>
title: <short-descriptive-title>
severity: <SEV-1|SEV-2|SEV-3|SEV-4>
service: <service-name>
environment: <prod|staging|dev>
category: <outage|degradation|security|data-loss|deployment-failure>
status: <active|investigating|mitigated|resolved>
owner: <owner-name>
assigned-to: <on-call-engineer>
date: <YYYY-MM-DD>
duration: <time-to-resolve>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
tags:
  - incident
  - <technology>
  - <issue-type>
  - <severity-tag>
  - <environment>
  - <service-area>
related_runbooks:
  - "[[RB-xxx-title]]"
related_incidents:
  - "[[INC-xxx-title]]"
---

## Summary

<What happened, when it started, what was affected, and scope of user impact.>

## Symptoms

- <Alert name and timestamp>
- <User-facing error or degraded behavior>
- <Metric anomaly observed on dashboard>

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | <count or %> |
| Services degraded | <list> |
| Revenue impact | <estimate or N/A> |
| Duration | <HH:MM UTC → HH:MM UTC> |
| Data loss | <none / describe> |

## Root Cause

1. <Hypothesis explored — ruled out>
2. <Hypothesis explored — ruled out>
3. **Confirmed:** <Root cause with supporting evidence>

## Diagnosis

1. <Step with command/output>
   ```bash
   <command>
   ```
2. <Step with command/output>
   ```bash
   <command>
   ```
3. <Additional diagnostic action>

## Resolution

1. **Mitigate:** <Immediate action to stop bleeding>
   ```bash
   <command>
   ```
2. **Fix:** <Action addressing root cause>
   ```bash
   <command>
   ```
3. **Verify:** <Confirmation service recovered>
   ```bash
   <command>
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| No progress in 15 min | Page senior on-call | PagerDuty |
| SEV-1 customer impact | Page EM + IC | #incident-response |
| Data integrity risk | Engage DB team | #data-eng |
| Security suspected | Engage SecOps | #security-urgent |

## Retro

**Went well:**
- <Effective aspect of response>

**Improve:**
- <Gap identified>

**Action items:**
- [ ] <Concrete follow-up task>
- [ ] <Concrete follow-up task>

## Links

- Runbooks: [[RB-xxx-title]]
- Related: [[INC-xxx-title]]
