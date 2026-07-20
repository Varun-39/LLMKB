---
id: ESC-001
title: Platform-Wide Incident Escalation Rules
type: escalation
scope: platform-wide
status: active
owner: SRE Leadership
approved_by: VP Engineering
effective_date: 2026-01-15
review_date: 2026-07-15
created: 2026-01-15
updated: 2026-05-22
last_triggered: 2026-05-22
tags:
  - escalation
  - platform
  - prod
  - incident-response
related_runbooks:
  - "[[RB-005-database-timeout-connection-exhaustion]]"
  - "[[RB-006-failed-deployment-rollback]]"
  - "[[RB-007-pod-crash-investigation]]"
related_incidents:
  - "[[INC-003-k8s-crashloopbackoff-auth]]"
  - "[[INC-006-disk-full-db-volume]]"
  - "[[INC-011-rollback-failed-frontend]]"
related_guardrails:
  - "[[GR-001-database-migration-guardrails]]"
related_kb: []
---

## Purpose

This document defines the mandatory escalation rules for all production incidents across the platform. It ensures that issues reach the right people at the right time, prevents responder fatigue from over-escalation, and guarantees that customer-impacting events receive executive visibility within contractual SLA windows.

## Scope

| Attribute | Value |
|-----------|-------|
| Service(s) | All production services (auth-service, payment-service, api-gateway, checkout-service) |
| Team(s) | SRE, Platform Engineering, DBA, Application Teams |
| Hours | 24/7 |
| On-call tool | PagerDuty |

## Severity Definitions

| Severity | Definition | Response Time | Resolution Target |
|----------|-----------|---------------|-------------------|
| SEV-1 | Full service outage or >50% of users impacted; revenue pathway blocked; data integrity at risk | Immediate (< 5 min) | < 1 hour |
| SEV-2 | Degraded service; 5–50% of users impacted; elevated error rates; no data loss | < 15 min | < 4 hours |
| SEV-3 | Internal tooling issue; no direct customer impact; workaround available | < 1 hour | < 24 hours |
| SEV-4 | Minor anomaly; informational alert; no action required immediately | Next business day | < 1 week |

## Escalation Matrix

### Tier 1: On-Call Engineer

| Trigger | Action | Time Limit |
|---------|--------|-----------|
| Alert fires | Acknowledge in PagerDuty, begin triage | 5 min to acknowledge |
| Initial triage complete | Classify severity, begin mitigation per runbook | 15 min |
| Cannot resolve or no progress | Escalate to Tier 2 | 30 min max at Tier 1 |

### Tier 2: Senior On-Call / Tech Lead

| Trigger | Action | Time Limit |
|---------|--------|-----------|
| Tier 1 escalation received | Join incident channel, assess root cause depth | 10 min to respond |
| Mitigation unsuccessful or scope expanding | Escalate to Tier 3 | 30 min max at Tier 2 |
| Cross-team dependency identified | Loop in dependent team lead directly | Immediately |
| Database-related root cause | Engage DBA team in #data-eng | Immediately |

### Tier 3: Engineering Manager / Incident Commander

| Trigger | Action | Time Limit |
|---------|--------|-----------|
| Tier 2 escalation received | Declare formal incident, assign IC, open war room | 10 min |
| SEV-1 with confirmed customer impact | Notify executive stakeholders and Customer Success | Within 30 min |
| Resolution requires emergency change approval | Approve change, document risk acceptance | As needed |
| External communication required | Authorize status page update | Within 15 min of customer impact confirmation |

### Tier 4: VP Engineering / Executive

| Trigger | Action | Time Limit |
|---------|--------|-----------|
| SEV-1 outage > 1 hour | Provide status update to executive team | Every 30 min |
| Data breach or security incident suspected | Engage Legal and SecOps | Immediately |
| Enterprise customer SLA breach confirmed | Authorize proactive customer communication | Within 1 hour |
| Revenue impact exceeds $50K estimated | Join incident call, authorize resource allocation | Immediately |

## Automatic Escalation Rules

These escalations are enforced by PagerDuty automation and fire regardless of manual decisions:

| Condition | Auto-Escalation | Channel |
|-----------|-----------------|---------|
| SEV-1 unacknowledged > 5 min | Page Tier 2 + backup on-call | PagerDuty |
| SEV-1 unresolved > 30 min | Page Tier 3 (EM) | PagerDuty |
| SEV-1 unresolved > 60 min | Notify Tier 4 (VP Eng) | PagerDuty + email |
| SEV-2 unacknowledged > 10 min | Page backup on-call | PagerDuty |
| SEV-2 unresolved > 2 hours | Escalate to Tier 2 | PagerDuty |
| Any alert unacknowledged > 15 min | Re-page + backup on-call | PagerDuty |
| Revenue-critical service (payment-service) SEV-1 > 15 min | Page EM + IC directly | PagerDuty P1 policy |

## Contact Directory

| Role | Name | Contact Method | Hours |
|------|------|----------------|-------|
| Primary on-call (auth) | Rotation (Sara Ndiaye, +2) | PagerDuty | 24/7 |
| Primary on-call (payments) | Rotation (Priya Sharma, +2) | PagerDuty | 24/7 |
| Backup on-call | Secondary rotation | PagerDuty | 24/7 |
| Tech Lead — Auth | Sara Ndiaye | Slack DM + phone | Business hours; PagerDuty for SEV-1 |
| Tech Lead — Payments | Priya Sharma | Slack DM + phone | Business hours; PagerDuty for SEV-1 |
| Engineering Manager | Alex Chen | PagerDuty + phone | 24/7 for SEV-1/SEV-2 |
| DBA Team | Database Engineering | #data-eng Slack | 24/7 |
| Platform/SRE | Platform Engineering | #platform-support Slack | 24/7 |
| Security Team | SecOps | #security-urgent Slack | 24/7 |
| Customer Success | CS Leadership | #customer-comms Slack | Business hours; phone for SEV-1 |

## Communication Channels

| Channel | Purpose | Who Joins |
|---------|---------|-----------|
| #incident-response | Active incident coordination and decision-making | IC, on-call, affected service owners, EM |
| #platform-support | Infrastructure, node, cluster, and volume issues | Platform team, SRE |
| #data-eng | Database escalations (locks, disk, replication, timeouts) | DBA team, service owners |
| #infra-secrets | Secrets management and credential rotation issues | Secrets team, SRE |
| #customer-comms | Customer-facing status communication drafting | CS team, EM, IC |
| Status page | External communication to customers | IC approval required before any update |

## Decision Criteria

### When to Escalate (Do Not Wait)

- You have been troubleshooting for 15 minutes with no forward progress
- Error rate or impact scope is increasing, not stabilizing
- You lack the access, permissions, or domain knowledge to proceed
- Multiple services are affected or cascading failures are evident
- Customer complaints are arriving through support channels
- You are unsure about the correct severity — escalate and let Tier 2 downgrade if appropriate
- The issue involves revenue-critical paths (payments, checkout)

### When NOT to Escalate

- Alert is a documented false positive with suppression scheduled
- Issue is isolated to staging or dev with no production risk
- Self-healing is in progress and metrics show clear recovery trajectory
- Issue falls within a scheduled maintenance window (verify in #platform-support)
- Alert threshold is known to be overly sensitive (document and tune post-incident)

## Post-Incident Requirements

| Severity | Post-Mortem Required | Timeline | Template |
|----------|---------------------|----------|----------|
| SEV-1 | Yes — full post-mortem with root cause, timeline, and action items | Within 3 business days | [[Incident Template]] |
| SEV-2 | Yes — summary post-mortem with action items | Within 5 business days | [[Incident Template]] |
| SEV-3 | Optional — at team discretion | Within 1 week | [[Incident Template]] |
| SEV-4 | No | N/A | N/A |

## Incident Commander Handoff

### Handoff Protocol

1. Outgoing owner posts in `#incident-response`: "Handing IC to @<name>. Current state: <one-line summary>."
2. Incoming IC acknowledges: "IC accepted by @<name>. Next update in <X> min."
3. IC pins the incident summary message and owns all external/internal status updates from this point.
4. No IC handoff during active mitigation steps — wait for a stable checkpoint.

### Status Update Cadence

| Severity | Update Frequency | Audience |
|----------|------------------|----------|
| SEV-1 | Every 30 min | #incident-response + exec stakeholders + status page |
| SEV-2 | Every 60 min | #incident-response |
| SEV-3 | At resolution | Affected team only |

### Status Update Template

```
[INCIDENT UPDATE] <INC-id> — <severity>
Status: <investigating | mitigating | monitoring | resolved>
Impact: <current user/service impact>
Actions: <what we're doing now>
Next update: <time UTC>
IC: <name>
```

## Test Schedule

| Field | Value |
|-------|-------|
| Last tested | 2026-04-01 |
| Next test due | 2026-07-01 |
| Test method | Quarterly tabletop exercise + PagerDuty dry-run page |
| Test owner | SRE Leadership |

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-01-15 | SRE Leadership | Initial publication |
| 2026-03-10 | Priya Sharma | Added revenue-critical service auto-escalation rule after INC-018 |
| 2026-04-15 | Alex Chen | Updated Tier 3 external comms timeline after INC-011 review |
| 2026-05-22 | Sara Ndiaye | Added secrets management channel after INC-003 |
