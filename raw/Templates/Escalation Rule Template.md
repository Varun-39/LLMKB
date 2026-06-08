---
id: ESC-<NNN>
title: <service-or-domain> Escalation Rules
type: escalation
scope: <service-name|domain|platform-wide>
status: <active|draft|deprecated>
owner: <owner-name>
approved_by: <approver-name>
effective_date: <YYYY-MM-DD>
review_date: <YYYY-MM-DD>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
tags:
  - escalation
  - <service-area>
  - <environment>
related_runbooks:
  - "[[RB-xxx-title]]"
---

## Purpose

<One sentence: what does this escalation document cover and for which service/team.>

## Scope

| Attribute | Value |
|-----------|-------|
| Service(s) | <service-name> |
| Team(s) | <responsible team> |
| Hours | <24/7 or business hours only> |
| On-call tool | <PagerDuty / Opsgenie / manual> |

## Severity Definitions

| Severity | Definition | Response Time | Resolution Target |
|----------|-----------|---------------|-------------------|
| SEV-1 | Full service outage, customer-facing impact, data at risk | Immediate (< 5 min) | < 1 hour |
| SEV-2 | Degraded service, partial impact, elevated error rates | < 15 min | < 4 hours |
| SEV-3 | Internal tooling issue, no customer impact | < 1 hour | < 24 hours |
| SEV-4 | Minor anomaly, informational, no action needed now | Next business day | < 1 week |

## Escalation Matrix

### Tier 1: On-Call Engineer

| Trigger | Action | Time Limit |
|---------|--------|-----------|
| Alert fires | Acknowledge, begin triage | 5 min to acknowledge |
| Initial triage complete | Determine severity, begin mitigation | 15 min |
| Cannot resolve | Escalate to Tier 2 | 30 min max at Tier 1 |

### Tier 2: Senior On-Call / Tech Lead

| Trigger | Action | Time Limit |
|---------|--------|-----------|
| Tier 1 escalation received | Join incident, assess root cause | 10 min to respond |
| Mitigation unsuccessful | Escalate to Tier 3 | 30 min max at Tier 2 |
| Cross-team dependency identified | Loop in dependent team lead | Immediately |

### Tier 3: Engineering Manager / Incident Commander

| Trigger | Action | Time Limit |
|---------|--------|-----------|
| Tier 2 escalation received | Declare formal incident, assign IC | 10 min |
| SEV-1 with customer impact | Notify executive stakeholders | Within 30 min |
| Resolution requires change approval | Approve emergency change | As needed |

### Tier 4: VP Engineering / Executive

| Trigger | Action | Time Limit |
|---------|--------|-----------|
| Outage > 1 hour | Status update to exec team | Every 30 min |
| Data breach suspected | Engage legal + security | Immediately |
| Customer SLA breach | Authorize customer communication | Within 1 hour |

## Automatic Escalation Rules

These escalations happen automatically (timer-based) regardless of manual decisions:

| Condition | Auto-Escalation | Channel |
|-----------|-----------------|---------|
| SEV-1 unacknowledged > 5 min | Page Tier 2 | PagerDuty |
| SEV-1 unresolved > 30 min | Page Tier 3 | PagerDuty |
| SEV-1 unresolved > 60 min | Notify Tier 4 | PagerDuty + email |
| SEV-2 unresolved > 2 hours | Escalate to Tier 2 | PagerDuty |
| Any alert unacknowledged > 15 min | Re-page + backup on-call | PagerDuty |

## Contact Directory

| Role | Name | Contact Method | Hours |
|------|------|----------------|-------|
| Primary on-call | <name or "rotation"> | PagerDuty | 24/7 |
| Backup on-call | <name or "rotation"> | PagerDuty | 24/7 |
| Tech Lead | <name> | Slack DM + phone | Business hours |
| Engineering Manager | <name> | PagerDuty + phone | 24/7 for SEV-1 |
| DBA Team | <team-name> | #data-eng Slack | 24/7 |
| Platform/SRE | <team-name> | #platform-support Slack | 24/7 |
| Security Team | <team-name> | #security-urgent Slack | 24/7 |
| Customer Success | <team-name> | #customer-comms Slack | Business hours |

## Communication Channels

| Channel | Purpose | Who Joins |
|---------|---------|-----------|
| #incident-response | Active incident coordination | IC, on-call, affected service owners |
| #platform-support | Infrastructure/node/cluster issues | Platform team |
| #data-eng | Database escalations | DBA team |
| #customer-comms | Customer-facing communication | CS team, EM |
| Status page | External communication | IC approval required |

## Decision Criteria

### When to Escalate (Don't Wait)

- You've been troubleshooting for 15 min with no progress
- Error rate is climbing, not stabilizing
- You don't have access or knowledge to fix the issue
- Multiple services are affected
- Customer complaints are arriving
- You are unsure about the severity — escalate and let Tier 2 downgrade if needed

### When NOT to Escalate

- Alert is a known false positive (document and suppress)
- Issue is in staging only with no prod risk
- Self-healing already in progress and metrics are recovering
- Scheduled maintenance window (check the calendar)

## Post-Incident Requirements

| Severity | Post-Mortem Required | Timeline |
|----------|---------------------|----------|
| SEV-1 | Yes — full post-mortem with action items | Within 3 business days |
| SEV-2 | Yes — brief summary + action items | Within 5 business days |
| SEV-3 | Optional — at team discretion | Within 1 week |
| SEV-4 | No | N/A |

## Revision History

| Date | Author | Change |
|------|--------|--------|
| <YYYY-MM-DD> | <name> | Initial publication |
| <YYYY-MM-DD> | <name> | <what changed> |
