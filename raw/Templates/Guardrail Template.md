---
id: GR-<NNN>
title: <guardrail-rule-name>
type: guardrail
scope: <deployment|database|infrastructure|security|operations>
enforcement: <mandatory|advisory|automated>
status: <active|draft|deprecated>
owner: <owner-name>
approved_by: <approver-name>
effective_date: <YYYY-MM-DD>
review_date: <YYYY-MM-DD>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
tags:
  - guardrail
  - <scope>
  - <technology>
  - <environment>
related_incidents:
  - "[[INC-xxx-title]]"
---

## Rule Statement

<One clear sentence stating what MUST or MUST NOT be done. Write as an imperative.>

**Example:** "Database schema migrations with exclusive locks MUST NOT run during peak traffic hours (08:00–22:00 UTC)."

## Rationale

<Why this guardrail exists. Reference the incident(s) that motivated it.>

- Root cause incident: [[INC-xxx-title]]
- Business impact that triggered this rule: <brief description>
- Frequency of past violations: <how often this has gone wrong>

## Scope

| Attribute | Value |
|-----------|-------|
| Applies to | <teams, services, or environments> |
| Enforcement level | <mandatory / advisory / automated> |
| Environments | <prod / staging / all> |
| Exceptions | <who can grant exceptions and how> |

## Rule Details

### What is Prohibited / Required

| Allowed |  Prohibited |
|-----------|--------------|
| <permitted action> | <prohibited action> |
| <permitted action> | <prohibited action> |
| <permitted action> | <prohibited action> |

### Conditions / Thresholds

| Condition | Threshold |
|-----------|-----------|
| <when does this rule apply> | <specific number or time window> |
| <when is it relaxed> | <maintenance window, with approval> |

### Exception Process

1. <Who can request an exception>
2. <Who approves it>
3. <How to document the exception>
4. <Time limit on exceptions>

## Detection / Enforcement

### How Violations Are Detected

- <Monitoring alert, CI/CD check, manual review>
- <Tool or dashboard used>
- <Frequency of checking>

### Automated Enforcement (if applicable)

```yaml
# Example: OPA/Kyverno policy, CI pipeline check, or admission webhook
<policy-definition-or-command>
```

### Manual Enforcement

- <Code review checklist item>
- <Deployment checklist item>
- <Audit schedule>

## Response to Violations

| Severity of Violation | Response |
|-----------------------|----------|
| During incident | Revert immediately, document in post-mortem |
| Caught pre-production | Block merge/deploy until resolved |
| Caught post-production (no impact) | Create follow-up ticket, no revert needed |
| Repeated violations | Escalate to engineering manager |

## Related Guardrails

- [[GR-xxx-title]] — <related rule>

## Revision History

| Date | Author | Change |
|------|--------|--------|
| <YYYY-MM-DD> | <name> | Initial publication |
| <YYYY-MM-DD> | <name> | <what changed and why> |
