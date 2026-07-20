---
id: RB-035
title: Incident Response Checklist and Communication Protocol
service: "*"
related_services:
  - all-services
severity: SEV-1
environment: prod
category: deployment
risk_level: low
estimated_duration: "N/A"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - incident-response
  - communication
  - checklist
  - process
  - prod
related_incidents: []
related_runbooks:
  - "[[RB-001-payment-gateway-oom-recovery]]"
  - "[[RB-006-failed-deployment-rollback]]"
related_guardrails:
  - "[[Escalation Rules]]"
  - "[[Guardrails]]"
---

## Purpose

Provide a structured incident response protocol covering roles, communication, severity classification, and post-incident procedures.

**Desired outcome:** Incidents handled efficiently with clear communication, appropriate escalation, and documented learnings.

## Success Criteria

- Incident commander assigned within 5 minutes
- Status page updated within 10 minutes (SEV-1)
- Stakeholders notified via appropriate channels
- Incident documented in wiki within 24 hours
- Post-incident review scheduled within 48 hours

## Scope

| Attribute | Value |
|-----------|-------|
| Service | All services |
| Environments | prod |
| Use when | Any production incident requiring coordinated response |
| Do NOT use when | Non-production issues or planned maintenance |
| Risk level | Low (this is a process guide) |
| Estimated duration | Varies by incident |
| Approval required | No |

## Severity Classification

| Severity | Criteria | Response Time | Escalation |
|----------|----------|---------------|------------|
| SEV-1 | Full outage, data loss risk, revenue-impacting | 5 min | Page EM, IC, status page |
| SEV-2 | Degraded service, partial outage, high error rate | 15 min | Page on-call, notify EM |
| SEV-3 | Minor degradation, no user impact, internal tooling | 1 hour | Notify on-call via Slack |

## Incident Commander Responsibilities

1. **Acknowledge** the incident within SLA
2. **Assess** severity and blast radius
3. **Communicate** — open incident channel, post first update
4. **Delegate** investigation tasks to responders
5. **Coordinate** mitigation efforts
6. **Update** status page and stakeholders at regular intervals
7. **Declare resolution** when success criteria met
8. **Document** timeline and actions in incident file

## Communication Protocol

### First 5 Minutes (SEV-1/SEV-2)

```
1. Acknowledge PagerDuty alert
2. Open #incident-YYYY-MM-DD-<slug> Slack channel
3. Post initial assessment:
   "INCIDENT: [service] - [symptom]. Investigating. Impact: [blast radius]. ETA: unknown."
4. Update status page: "Investigating - We are aware of issues with [service]"
```

### Every 15 Minutes

```
1. Post update in incident channel (even if "still investigating")
2. Update status page if status changed
3. Notify customer success if customer-facing
```

### Resolution

```
1. Post final update: "RESOLVED: [service] - [root cause]. [duration] total impact."
2. Update status page: "Resolved"
3. Send recovery notification to affected customers (if applicable)
4. Schedule post-incident review
```

## Post-Incident Process

1. **Within 24 hours:** Create incident file (wiki/Incidents/INC-NNN-slug.md)
2. **Within 48 hours:** Schedule blameless post-incident review
3. **During review:** Identify contributing factors, action items, process improvements
4. **After review:** File action items as tracked issues with owners and due dates
5. **Monthly:** Review open action items from past incidents

## Incident File Template

Create at `wiki/Incidents/INC-<NNN>-<slug>.md` following the existing format:

- YAML frontmatter (id, title, severity, service, environment, category, date, duration, tags)
- Summary, Symptoms, Impact, Timeline, Diagnosis, Resolution
- Escalation triggers
- Post-Incident Review (what went well, what needs improvement, action items)
- Links to runbooks, related incidents

## Notes

- **Blameless culture:** Focus on systems and processes, not individuals. "How did the system allow this?" not "Who did this?"
- **Don't skip the review** for SEV-3 incidents — small issues reveal systemic problems.
- **Action items without owners and due dates are wishes, not actions.**
- **Record the incident even if it was brief** — patterns emerge from aggregated data.
- See [[Escalation Rules]] and [[Guardrails]] for organizational escalation policies.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Run a tabletop exercise simulating a SEV-1 incident.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team + Engineering Leadership | Initial publication |
