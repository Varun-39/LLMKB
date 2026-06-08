---
id: META-<NNN>
title: <standard-or-policy-name>
type: metadata-standard
scope: <vault-wide|incidents|runbooks|kb-articles>
status: <active|draft|deprecated>
owner: <owner-name>
approved_by: <approver-name>
effective_date: <YYYY-MM-DD>
review_date: <YYYY-MM-DD>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
tags:
  - metadata
  - standards
  - governance
---

## Purpose

<One sentence: what does this standard define and why does it exist.>

## Scope

<Which note types, teams, or systems does this standard apply to.>

## Standard Definition

### Required Fields

| Field | Type | Allowed Values | Example |
|-------|------|----------------|---------|
| `id` | string | `<PREFIX>-<NNN>` | `INC-001` |
| `title` | string | Free text, max 60 chars | `Payment Service OOM Crash` |
| `severity` | enum | `SEV-1`, `SEV-2`, `SEV-3`, `SEV-4` | `SEV-1` |
| `status` | enum | <list allowed values> | `active` |
| `owner` | string | Full name | `Priya Sharma` |
| `created` | date | `YYYY-MM-DD` | `2026-06-02` |
| `updated` | date | `YYYY-MM-DD` | `2026-06-02` |
| `tags` | list | From approved taxonomy | `[incident, kubernetes]` |

### Optional Fields

| Field | Type | When to Use |
|-------|------|-------------|
| `duration` | string | Incidents only |
| `expires` | date | KB articles with time-sensitive content |
| `vendor_case_id` | string | Vendor notes only |

### Naming Conventions

| Note Type | Pattern | Example |
|-----------|---------|---------|
| Incident | `INC-<NNN>-<kebab-title>.md` | `INC-001-payment-service-oom-crash.md` |
| Runbook | `RB-<NNN>-<service>-<issue>.md` | `RB-002-kubernetes-oom-remediation.md` |
| KB Article | `KB-<NNN>-<topic>.md` | `KB-001-jvm-heap-tuning.md` |
| Vendor Note | `VN-<NNN>-<vendor>-<issue>.md` | `VN-001-aws-rds-certificate-rotation.md` |
| Guardrail | `GR-<NNN>-<rule-name>.md` | `GR-001-no-ddl-during-peak.md` |
| Escalation | `ESC-<NNN>-<scope>.md` | `ESC-001-payment-service-escalation.md` |

### Tag Taxonomy

| Category | Allowed Tags |
|----------|-------------|
| Note Type | `incident`, `runbook`, `kb`, `vendor-note`, `guardrail`, `escalation` |
| Technology | `kubernetes`, `postgres`, `redis`, `kafka`, `aws`, `docker` |
| Issue Type | `oom`, `disk`, `cpu`, `memory`, `network`, `timeout`, `deployment` |
| Severity | `critical`, `high`, `medium`, `low` |
| Environment | `prod`, `staging`, `dev` |
| Service | `payments`, `auth`, `api`, `reporting`, `notifications` |

## Compliance

- All notes MUST include the required fields before publishing
- Tags MUST come from the approved taxonomy (propose new tags via PR)
- Dates MUST use `YYYY-MM-DD` format (Dataview compatibility)
- Wikilinks in frontmatter MUST be quoted: `"[[RB-001-title]]"`

## Review Schedule

This standard is reviewed quarterly. Next review: <YYYY-MM-DD>.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| <YYYY-MM-DD> | <name> | Initial publication |
