---
id: META-<NNN>
title: <standard-or-policy-name>
type: metadata-standard
version: 1.0.0
scope: <vault-wide|incidents|runbooks|kb-articles|policies>
status: <active|draft|deprecated|under-review>
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

This document defines the **metadata schema, naming conventions, and tag taxonomy** that every note in the vault must follow. It exists to keep the knowledge base consistent, queryable via Dataview, and navigable via wikilinks.

> Replace this paragraph with the specific purpose of this standard instance. State (1) what it defines, (2) why it exists, and (3) what breaks if it is not followed.

## Scope

This standard applies to **all note types in the vault** unless a more specific standard overrides it. The note types governed are:

- Incidents (`INC-`)
- Runbooks (`RB-`)
- KB Articles (`KB-`)
- Vendor Notes (`VN-`)
- Guardrails (`GR-`)
- Escalation Rules (`ESC-`)
- Metadata Standards (`META-`)

> Replace the scope above to narrow it if this standard governs only one note type.

## Versioning

This standard is versioned using **semantic versioning** (`MAJOR.MINOR.PATCH`) in the `version` frontmatter field:

| Bump | When |
|------|------|
| **MAJOR** | A required field is added/removed, or a breaking taxonomy change occurs. Existing notes may become non-compliant and need migration. |
| **MINOR** | A new optional field or allowed value is added. Existing notes remain compliant. |
| **PATCH** | Typo fixes, clarifications, or formatting — no schema change. |

Notes may record which standard version they comply with via an optional `schema_version` field. When the MAJOR version changes, see the [Migration Guide](#migration-guide).

## Field Requirements by Document Type

Not all fields apply to all note types. The following cross-table is the **single source of truth** for which fields are required (R), optional (O), or not applicable (--) per document type.

| Field | INC | RB | KB | VN | GR | ESC | META |
|-------|:---:|:--:|:--:|:--:|:--:|:---:|:----:|
| `id` | R | R | R | R | R | R | R |
| `title` | R | R | R | R | R | R | R |
| `status` | R | R | R | R | R | R | R |
| `owner` | R | R | R | R | R | R | R |
| `created` | R | R | R | R | R | R | R |
| `updated` | R | R | R | R | R | R | R |
| `tags` | R | R | R | R | R | R | R |
| `severity` | R | R | -- | R | O | O | -- |
| `service` | R | R | O | O | O | O | -- |
| `environment` | R | R | O | O | O | O | -- |
| `category` | R | R | R | O | O | -- | -- |
| `assigned-to` | R | -- | -- | -- | -- | -- | -- |
| `date` | R | -- | -- | -- | -- | -- | -- |
| `duration` | O | -- | -- | -- | -- | -- | -- |
| `last-updated` | -- | R | -- | -- | -- | -- | -- |
| `audience` | -- | -- | R | -- | -- | -- | -- |
| `reviewer` | -- | -- | R | -- | -- | -- | -- |
| `expires` | -- | -- | O | -- | -- | -- | -- |
| `vendor` | -- | -- | -- | R | -- | -- | -- |
| `vendor_case_id` | -- | -- | -- | O | -- | -- | -- |
| `enforcement` | -- | -- | -- | -- | R | -- | -- |
| `approved_by` | -- | -- | -- | -- | R | R | R |
| `version` | -- | -- | -- | -- | -- | -- | R |

**Legend:** R = Required, O = Optional, -- = Not applicable

## Field Definitions

### Universal Required Fields (all document types)

| Field | Type | Allowed Values | Example |
|-------|------|----------------|---------|
| `id` | string | `<PREFIX>-<NNN>` (zero-padded 3-digit) | `INC-001` |
| `title` | string | Free text, max 60 chars, no leading/trailing spaces | `Payment Service OOM Crash` |
| `status` | enum | See [Status Values](#status-values-by-document-type) | `active` |
| `owner` | string | Full name of responsible person | `Priya Sharma` |
| `created` | date | `YYYY-MM-DD` | `2026-06-02` |
| `updated` | date | `YYYY-MM-DD` | `2026-06-02` |
| `tags` | list | From [approved taxonomy](#tag-taxonomy) | `[incident, kubernetes]` |

### Conditional Fields

| Field | Type | Allowed Values | Applies To |
|-------|------|----------------|-----------|
| `severity` | enum | `SEV-1`, `SEV-2`, `SEV-3`, `SEV-4` | INC, RB, VN (req); GR, ESC (opt) |
| `service` | string | lowercase, hyphenated service name | INC, RB (req) |
| `environment` | enum | `prod`, `staging`, `dev` | INC, RB (req) |
| `category` | enum | Type-specific (see below) | INC, RB, KB |
| `version` | string | Semantic version `MAJOR.MINOR.PATCH` | META (req) |

### Status Values by Document Type

The allowed `status` values differ per document type:

| Document Type | Allowed `status` Values |
|---------------|-------------------------|
| Incident (INC) | `active`, `investigating`, `mitigated`, `resolved` |
| Runbook (RB) | `active`, `deprecated`, `under-review` |
| KB Article (KB) | `published`, `draft`, `under-review`, `deprecated` |
| Vendor Note (VN) | `active`, `resolved`, `monitoring`, `acknowledged` |
| Guardrail (GR) | `active`, `draft`, `deprecated` |
| Escalation (ESC) | `active`, `draft`, `deprecated` |
| Metadata Standard (META) | `active`, `draft`, `deprecated`, `under-review` |

## Naming Conventions

Pattern syntax:
- `<NNN>` = zero-padded 3-digit sequence (`001`, `002`, ...)
- `<slug>` = lowercase kebab-case (words separated by **single** hyphens)
- Segments within a filename are joined by single hyphens; there are **no** double hyphens.

| Note Type | Pattern | Example |
|-----------|---------|---------|
| Incident | `INC-<NNN>-<slug>.md` | `INC-001-payment-service-oom-crash.md` |
| Runbook | `RB-<NNN>-<service>-<issue>.md` | `RB-002-kubernetes-oom-remediation.md` |
| KB Article | `KB-<NNN>-<topic-slug>.md` | `KB-001-jvm-heap-tuning.md` |
| Vendor Note | `VN-<NNN>-<vendor>-<issue>.md` | `VN-001-aws-rds-certificate-rotation.md` |
| Guardrail | `GR-<NNN>-<rule-slug>.md` | `GR-001-no-ddl-during-peak.md` |
| Escalation | `ESC-<NNN>-<scope>.md` | `ESC-001-payment-service-escalation.md` |
| Metadata Standard | `META-<NNN>-<slug>.md` | `META-001-vault-metadata-standard.md` |

## Tag Taxonomy

| Category | Allowed Tags |
|----------|-------------|
| Note Type | `incident`, `runbook`, `kb`, `vendor-note`, `guardrail`, `escalation`, `metadata` |
| Technology | `kubernetes`, `postgres`, `redis`, `kafka`, `aws`, `docker`, `nginx` |
| Issue Type | `oom`, `disk`, `cpu`, `memory`, `network`, `timeout`, `deployment`, `crashloop` |
| Severity | `critical`, `high`, `medium`, `low` |
| Environment | `prod`, `staging`, `dev` |
| Service | `payments`, `auth`, `api`, `reporting`, `notifications` |

New tags MUST be proposed via PR and added to this table (a MINOR version bump) before use.

## Compliance Rules

- All notes MUST include every field marked R for their document type before publishing
- `severity` is **not** universally required — apply it only to the document types marked in the [field requirements table](#field-requirements-by-document-type)
- Tags MUST come from the approved taxonomy; one-off tags are not permitted
- Dates MUST use `YYYY-MM-DD` format (required for Dataview date parsing)
- Wikilinks in frontmatter MUST be quoted: `"[[RB-001-title]]"`
- `id` in frontmatter MUST match the filename prefix and number

## Validation and Enforcement

Standards are only as good as their enforcement. This standard is intended to be checked automatically:

- **Linting script:** `scripts/validate-metadata.py` *(planned)* — validates frontmatter against this schema, checks required fields per document type, verifies date formats, and flags non-taxonomy tags.
- **CI gate:** *(planned)* — run the validator on every PR; block merges that introduce non-compliant notes.
- **Manual review:** until automation lands, reviewers check frontmatter against the [field requirements table](#field-requirements-by-document-type) during PR review.

> Until the validation script exists, treat the field requirements table as the manual review checklist.

## Migration Guide

When this standard changes in a way that affects existing notes (a MAJOR version bump), follow this process:

1. **Announce** the change and the new version number in the team channel.
2. **Document** what changed in the [Revision History](#revision-history) below, including which fields/values were added, removed, or renamed.
3. **Identify** affected notes with a Dataview query or the validation script (e.g., notes missing a newly required field).
4. **Backfill** the affected notes. For a newly required field, add it with a sensible default or `unknown` placeholder, then refine.
5. **Set a deadline** — notes not migrated by the deadline are flagged `under-review`.
6. **Bump** the `version` field of this standard and update `effective_date`.

### Backwards Compatibility

- Notes record the standard version they were authored against via optional `schema_version`.
- A MINOR or PATCH change never invalidates an existing note.
- A MAJOR change may invalidate notes; those notes remain readable but are considered non-compliant until migrated.

## Review Schedule

This standard is reviewed **quarterly**.

| Field | Value |
|-------|-------|
| Last reviewed | `<YYYY-MM-DD>` |
| Next review due | `<YYYY-MM-DD>` |
| Review owner | `<owner-name>` |

## Revision History

| Date | Version | Author | Change |
|------|---------|--------|--------|
| `<YYYY-MM-DD>` | 1.0.0 | `<name>` | Initial publication |
| `<YYYY-MM-DD>` | `<x.y.z>` | `<name>` | `<what changed and why — reference affected fields>` |
