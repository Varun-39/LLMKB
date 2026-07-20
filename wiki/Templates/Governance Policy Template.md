---
id: GOV-<num>
title: <governance-policy-name>
type: governance-policy
version: 1.0.0
scope: <platform-wide|service-specific|team-specific|infrastructure>
enforcement: <mandatory|advisory|automated>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
tags:
  - governance
  - <category>
  - <scope>
  - <environment>
---

## Policy Statement

<One or two sentences clearly stating the policy in imperative language. This should be concise enough to stand alone as a summary.>

**Example:** "All production changes MUST go through the Change Advisory Board (CAB) approval process and be scheduled at least 24 hours in advance, except for emergency hotfixes following the emergency change protocol."

## Purpose & Rationale

<Why does this policy exist? What risk does it mitigate? What business or operational need does it address?>

- **Business justification:** <Impact of not having this policy — revenue, security, compliance, reliability>
- **Triggering event(s):** <Incident, audit finding, regulatory requirement, or organizational decision that prompted creation>
- **Risk mitigated:** <What could go wrong without this policy in place>

## Scope

| Attribute | Value |
|-----------|-------|
| Applies to | <teams, services, roles, or environments> |
| Enforcement level | <mandatory / advisory / automated> |
| Environments | <prod / staging / all> |
| Effective hours | <24/7 / business hours / specific window> |
| Exceptions authority | <who can grant exceptions> |

## Policy Details

### Requirements

<Numbered list of specific, actionable requirements that this policy mandates.>

1. <Requirement — use MUST, MUST NOT, SHALL, SHALL NOT for mandatory items>
2. <Requirement>
3. <Requirement>

### Prohibited Actions

| Prohibited | Reason |
|------------|--------|
| <action that is not allowed> | <why it is prohibited> |
| <action that is not allowed> | <why it is prohibited> |

### Permitted Actions

| Permitted | Conditions |
|-----------|-----------|
| <action that is allowed> | <under what conditions> |
| <action that is allowed> | <under what conditions> |

### Thresholds & Triggers

| Condition | Threshold / Criteria |
|-----------|---------------------|
| <when does this policy apply> | <specific number, time window, or criteria> |
| <when are exceptions permitted> | <approval, maintenance window, etc.> |

## Roles & Responsibilities

| Role | Responsibility |
|------|---------------|
| <role-name> | <what they are responsible for under this policy> |
| <role-name> | <what they are responsible for under this policy> |
| <role-name> | <what they are responsible for under this policy> |

## Compliance & Enforcement

### How Compliance Is Verified

- <Monitoring, auditing, review cadence, or tooling used to verify compliance>
- <Dashboard, report, or metric tracked>
- <Frequency of compliance checks>

### Automated Enforcement (if applicable)

```yaml
# Example: CI/CD gate, policy-as-code, admission controller, or automated audit
<policy-definition-or-command>
```

### Manual Enforcement

- <Review process or checklist item>
- <Audit schedule>
- <Reporting mechanism>

## Exception Process

1. **Request:** <Who can request an exception and how (channel, form, ticket)>
2. **Justification:** <What information must be provided — risk assessment, mitigation plan, time limit>
3. **Review:** <Who reviews the exception request and within what timeframe>
4. **Approval:** <Who has authority to approve — must be documented in writing>
5. **Documentation:** <Where is the exception logged — audit log, ticket, governance register>
6. **Expiry:** <Maximum duration of an exception — must have a defined end date>
7. **Renewal:** <Process if the exception needs to be extended>

## Non-Compliance Response

| Violation Type | Response |
|----------------|----------|
| First occurrence (low impact) | Notify team lead; create corrective action ticket |
| First occurrence (high impact) | Immediate remediation required; escalate to EM |
| Repeated violations (same team) | Escalate to VP Engineering; mandatory training |
| Violation during active incident | Revert immediately; document in post-mortem |
| Deliberate policy circumvention | Escalate to VP Engineering + HR |

## Communication & Training

| Aspect | Details |
|--------|---------|
| Announcement channel | <where was/will this policy be announced — Slack, email, wiki> |
| Training required | <yes/no — if yes, describe format and frequency> |
| Training audience | <who must complete training> |
| Acknowledgment required | <yes/no — do teams need to formally acknowledge this policy> |

## Metrics & Reporting

| Metric | Target | Measured By |
|--------|--------|-------------|
| <compliance metric> | <target percentage or threshold> | <tool or process> |
| <violation count> | <target: zero or below threshold> | <tool or process> |
| <audit completion rate> | <target percentage> | <tool or process> |

## Related Policies & Documents

- [[GOV-xxx-title]] — <related governance policy>
- [[GR-xxx-title]] — <related guardrail>
- [[ESC-xxx-title]] — <related escalation rule>
- <External reference: regulatory standard, framework, or vendor requirement>

## Review Schedule

| Field | Value |
|-------|-------|
| Review frequency | <quarterly / semi-annually / annually> |
| Next review date | <YYYY-MM-DD> |
| Review owner | <name or team> |
| Stakeholders consulted | <teams or roles consulted during review> |

## Revision History

| Date | Author | Change |
|------|--------|--------|
| <YYYY-MM-DD> | <name> | Initial publication |
| <YYYY-MM-DD> | <name> | <what changed and why> |
