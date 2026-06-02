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

## Scope

| | |
|---|---|
| **Service** | <service-name> |
| **Environments** | <prod, staging> |
| **Use when** | <trigger condition> |
| **Do NOT use when** | <exclusion criteria> |

## Prerequisites

- [ ] `kubectl` access to `<namespace>` confirmed
- [ ] VPN connected
- [ ] Monitoring dashboard accessible
- [ ] On-call role confirmed

## Required Tools

| Tool | Purpose |
|------|---------|
| `kubectl` | Pod/deployment operations |
| Grafana | Metric verification |
| Cloud console | Infrastructure checks |

## Triggers

- Alert: `<alert-name>` fires
- Symptom: <observable behavior>
- Metric: <threshold breached>

## Triage

1. Confirm alert is genuine
   ```bash
   <verification command>
   ```
2. Assess blast radius — isolated vs. widespread
   ```bash
   <command>
   ```
3. Wrong symptoms? → Try [[alternative-runbook]]

## Investigate

1. **Resource state**
   ```bash
   <command>
   ```
2. **Recent deployments**
   ```bash
   <command>
   ```
3. **Application logs**
   ```bash
   <command>
   ```
4. **Dependent services** — DB, queue, external APIs
5. **Change correlation** — deployment pipeline, infra changes

## Resolve

1. <Corrective action>
   ```bash
   <command>
   ```
2. <Corrective action>
   ```bash
   <command>
   ```
3. <Corrective action>
   ```bash
   <command>
   ```
4. Monitor 10 min before closing

## Verify

- [ ] All pods Running, 0 restarts in 5 min
- [ ] Error rate at baseline
- [ ] No new alerts in 15 min
- [ ] Health endpoint returns 200

```bash
<health check command>
```

## Rollback

1. Revert deployment
   ```bash
   kubectl rollout undo deployment/<name> -n <namespace>
   ```
2. Restore previous resource config
3. Notify #incident-response

## Escalation

| Trigger | Escalate to | Channel |
|---------|-------------|---------|
| No fix in 30 min | Senior on-call | #incident-response |
| SEV-1 customer impact | EM + IC | PagerDuty escalation |
| Infra-level failure | Platform/SRE | #platform-support |
| Security concern | SecOps | #security-urgent |

## Notes

- <Caveats, known quirks, historical context>
- Last tested: <YYYY-MM-DD>
- Review cycle: Quarterly

## Links

- Incidents: [[INC-xxx-title]]
- Related: [[RB-xxx-title]]
