---
id: VN-<NNN>
title: <vendor-name> — <issue-or-advisory-title>
vendor: <vendor-name>
product: <product-or-service-name>
advisory_type: <bug|security-patch|deprecation|outage|maintenance|release-note>
severity: <critical|high|medium|low|informational>
status: <active|resolved|monitoring|acknowledged>
affected_services:
  - <service-name>
owner: <engineer-tracking-this>
vendor_case_id: <case-number-or-ticket-id>
vendor_url: <link-to-vendor-advisory-or-portal>
date_reported: <YYYY-MM-DD>
date_resolved: <YYYY-MM-DD or pending>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
tags:
  - vendor-note
  - <vendor-name>
  - <product>
  - <severity-tag>
  - <environment>
related_incidents:
  - "[[INC-xxx-title]]"
related_runbooks:
  - "[[RB-xxx-title]]"
---

## Advisory Summary

<One-paragraph summary of what the vendor communicated. Include: what is affected, what is the risk, and what action is required.>

## Affected Systems

| Attribute | Detail |
|-----------|--------|
| Vendor | <vendor-name> |
| Product/Service | <product-name, version> |
| Our affected services | <list of internal services impacted> |
| Environments | <prod, staging, dev> |
| Impact window | <start date → end date or "ongoing"> |

## Vendor Recommendation

<What the vendor says to do. Quote or paraphrase their guidance.>

1. <Recommended action from vendor>
2. <Recommended action from vendor>
3. <Timeline or SLA the vendor committed to>

## Our Response

### Actions Taken

1. <What we did in response>
2. <Mitigation applied internally>
3. <Patch deployed / config changed / monitoring added>

### Actions Pending

- [ ] <Follow-up step>
- [ ] <Validation after vendor patch>

## Risk Assessment

| Factor | Assessment |
|--------|-----------|
| Likelihood of impact | <high/medium/low> |
| Blast radius | <which users/services affected> |
| Data risk | <none/potential/confirmed> |
| Workaround available | <yes/no — describe> |

## Communication

| Audience | Notified | Channel | Date |
|----------|----------|---------|------|
| Engineering team | <yes/no> | <Slack channel or email> | <date> |
| Customers | <yes/no> | <status page or email> | <date> |
| Management | <yes/no> | <channel> | <date> |

## Timeline

| Date | Event |
|------|-------|
| <YYYY-MM-DD> | Vendor advisory published |
| <YYYY-MM-DD> | Internal triage completed |
| <YYYY-MM-DD> | Mitigation deployed |
| <YYYY-MM-DD> | Vendor patch applied |
| <YYYY-MM-DD> | Issue confirmed resolved |

## References

- Vendor advisory: <URL>
- Internal incident: [[INC-xxx-title]]
- Patch PR: <link>

## Revision History

| Date | Author | Change |
|------|--------|--------|
| <YYYY-MM-DD> | <name> | Initial note created |
