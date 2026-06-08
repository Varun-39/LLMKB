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

<What happened, when it started, what was affected, and scope of user impact. Keep to 2–3 sentences.>

## Symptoms

- <Alert name + timestamp that triggered investigation>
- <User-facing error or degraded behavior observed>
- <Metric anomaly on dashboard (be specific: metric name, value, threshold)>
- <Downstream service impact>

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | <count or percentage> |
| Services degraded | <list of services and severity of degradation> |
| Revenue impact | <estimated dollar amount or N/A> |
| Duration | <HH:MM UTC → HH:MM UTC (X min)> |
| Data loss | <none / describe extent> |
| SLA breach | <yes/no — which SLA> |

## Root Cause

1. <Hypothesis explored — ruled out, with evidence>
2. <Hypothesis explored — ruled out, with evidence>
3. **Confirmed:** <Root cause with supporting evidence (commit hash, config change, metric correlation)>

## Diagnosis

<Ordered steps taken to isolate the root cause. Include commands and their output.>

1. <Diagnostic step>
   ```bash
   <command>
   # <relevant output>
   ```
2. <Diagnostic step>
   ```bash
   <command>
   # <relevant output>
   ```
3. <Diagnostic step>
   ```bash
   <command>
   ```

## Resolution

1. **Mitigate:** <Immediate action to stop user impact>
   ```bash
   <command>
   ```
2. **Fix:** <Action addressing the root cause>
   ```bash
   <command>
   ```
3. **Verify:** <Confirmation that service recovered>
   ```bash
   <command>
   # <expected healthy output>
   ```

## Escalation

| Trigger | Action | Channel |
|---------|--------|---------|
| No progress in 15 min | Page senior on-call | PagerDuty |
| SEV-1 customer impact | Page EM + IC | #incident-response |
| Data integrity risk | Engage DBA team | #data-eng |
| Security suspected | Engage SecOps | #security-urgent |

## Post-Incident Review

**What went well:**
- <Effective aspect of the response>

**What needs improvement:**
- <Gap identified in monitoring, docs, or process>

**Action items:**
- [ ] <Concrete follow-up task with owner and due date>
- [ ] <Concrete follow-up task with owner and due date>
- [ ] <Concrete follow-up task with owner and due date>

## Links

- Runbooks: [[RB-xxx-title]]
- Related incidents: [[INC-xxx-title]]
- PR/commit: <link to fix>
- Post-mortem doc: <link if separate>

## Revision History

| Date | Author | Change |
|------|--------|--------|
| <YYYY-MM-DD> | <name> | Incident created |
| <YYYY-MM-DD> | <name> | Resolved, post-mortem added |
