---
id: VN-001
title: Jira — Operational Knowledge Source for Incident Response
category: vendor-note
vendor: Atlassian
product: Jira (Cloud / Data Center)
owner: SRE Leadership
last_reviewed: 2026-06-12
status: active
tags:
  - vendor-note
  - jira
  - atlassian
  - incident-management
  - change-management
  - knowledge-extraction
  - ai-retrieval
---

# Purpose

This document describes how Jira functions as an **operational knowledge source** within our incident response, problem management, and change management workflows. It defines what data to extract from Jira for knowledge base indexing, what to exclude, and how Jira relates to the broader operational documentation ecosystem (incidents, runbooks, KB articles, services, and escalation procedures).

This is not Jira product documentation. It is a vendor integration guide written for operations teams, SRE, incident managers, and AI knowledge retrieval systems.

# Vendor Overview

| Attribute | Value |
|-----------|-------|
| Vendor | Atlassian |
| Product | Jira (Cloud / Data Center) |
| Primary use | Issue tracking, incident tickets, change requests, problem records |
| Access URL | `https://<org>.atlassian.net` (Cloud) or internal instance |
| API | REST API v3 (Cloud) / v2 (Data Center) |
| Authentication | OAuth 2.0 / API token / Service account |
| Data residency | Confirm with IT — region-specific for Cloud |

# Role in the Environment

Jira serves as the **system of record** for:

1. **Incident tickets** — every production incident has a corresponding Jira issue linking to the post-mortem, runbook, and resolution steps.
2. **Problem records** — recurring incidents are grouped under problem tickets that track root cause analysis and permanent fixes.
3. **Change requests** — all production changes (deployments, migrations, infrastructure updates) are tracked through Jira change tickets.
4. **Operational tasks** — action items from post-mortems, guardrail violations, and capacity reviews.

Jira is **not** the source of truth for:
- Runbook content (lives in this wiki under `/Runbooks/`)
- Architecture documentation (lives under `/Architecture/`)
- Alert definitions (lives in PagerDuty / Prometheus configs)
- Real-time monitoring (lives in Grafana / Datadog)

# Supported Operational Processes

| Process | Jira Role | Key Project |
|---------|-----------|-------------|
| Incident Management | Ticket per incident; links to post-mortem and runbook | INC |
| Problem Management | Groups related incidents; tracks root cause investigation | PROB |
| Change Management | Change request tickets with approval workflows | CHG |
| Post-Mortem Action Items | Tasks created from incident reviews | INC or OPS |
| Guardrail Violations | Compliance tickets for repeated violations | GOV |
| Capacity Planning | Tracks capacity review outcomes and expansion requests | INFRA |

# Jira Projects

| Project Key | Name | Purpose | Ticket Types |
|-------------|------|---------|--------------|
| INC | Incidents | Production incident tracking | Incident, Sub-task |
| PROB | Problems | Root cause and recurring issue tracking | Problem, Investigation |
| CHG | Changes | Production change requests and approvals | Change Request, Emergency Change |
| OPS | Operations | Operational tasks, toil reduction, reliability work | Task, Sub-task |
| INFRA | Infrastructure | Capacity, scaling, infrastructure requests | Task, Epic |
| GOV | Governance | Compliance tracking, audit findings, guardrail exceptions | Compliance Issue, Exception Request |

# Ticket Lifecycle

## Incident Tickets (INC project)

```
Open → Triaging → Mitigating → Monitoring → Resolved → Closed
                                                 ↓
                                          Post-Mortem Linked
```

- **Open:** Alert fires, on-call creates ticket (or automation does)
- **Triaging:** Severity classified, responder assigned
- **Mitigating:** Active resolution in progress
- **Monitoring:** Fix applied, watching for recurrence
- **Resolved:** Service restored, customer impact ended
- **Closed:** Post-mortem complete, action items created

## Change Tickets (CHG project)

```
Draft → Submitted → Under Review → Approved → Implementing → Completed → Closed
                         ↓
                      Rejected (with reason)
```

## Problem Tickets (PROB project)

```
Open → Investigating → Root Cause Identified → Fix In Progress → Verified → Closed
```

# Important Fields

## Summary

**What it contains:** One-line description of the incident or change.

**Operational value:** Primary search key for retrieval. Must be descriptive enough to identify the issue without opening the ticket.

**Good example:** `auth-service CrashLoopBackOff due to corrupt base64 secret after credential rotation`

**Bad example:** `Auth down` or `Fix issue`

**AI relevance:** High — used for semantic search and similarity matching against incoming alerts.

## Description

**What it contains:** Full context including symptoms, affected services, initial hypothesis, links to dashboards and logs.

**Operational value:** Contains the initial responder's observations. Often includes command outputs, error messages, and environmental context not captured elsewhere.

**AI relevance:** High — richest source of diagnostic context. Extract error messages, service names, and symptoms for indexing.

**Structure expected:**
```
## Symptoms
- <observable indicators>

## Affected Services
- <service list>

## Initial Observations
- <commands run, outputs seen>

## Links
- Grafana: <url>
- PagerDuty: <url>
- Runbook: <wiki-link>
```

## Resolution

**What it contains:** Steps taken to resolve the issue. Includes commands, configuration changes, rollbacks, and verification steps.

**Operational value:** This is the single most valuable field for knowledge extraction. A well-written resolution field becomes reusable for future incidents.

**AI relevance:** Critical — primary target for RAG indexing. Resolution steps should be extractable as standalone remediation guidance.

**Structure expected:**
```
## Root Cause
<one-paragraph explanation>

## Fix Applied
1. <step with command>
2. <step with command>

## Verification
- <how we confirmed the fix worked>

## Prevention
- <what we'll do to prevent recurrence>
```

## Components

**What it contains:** Jira component field mapping to service names or infrastructure layers.

**Operational value:** Enables filtering incidents by service. Maps directly to the service catalog.

**AI relevance:** High — used for scoping retrieval to relevant services. Must match service names in this wiki's `/Services/` folder.

**Expected values:** `auth-service`, `payment-service`, `api-gateway`, `checkout-service`, `postgres-primary`, `pgbouncer`, `kubernetes`, `networking`

## Labels

**What it contains:** Freeform tags for categorization.

**Operational value:** Enables cross-cutting searches (e.g., all `database-lock` issues regardless of service).

**AI relevance:** Medium — useful for faceted retrieval but inconsistent across teams. Normalize before indexing.

**Standard labels:**
- `post-mortem-complete` / `post-mortem-pending`
- `customer-impacting` / `internal-only`
- `recurring-issue`
- `guardrail-violation`
- `emergency-change`
- `automation-failure`

## Priority

**What it contains:** Business priority (P1–P4) or severity mapping.

**Operational value:** Determines SLA and escalation path.

**Mapping to severity:**

| Jira Priority | Severity | Escalation |
|---------------|----------|-----------|
| P1 — Critical | SEV-1 | Immediate, auto-escalate per [[ESC-001-platform-wide-incident-escalation-rules]] |
| P2 — High | SEV-2 | 15 min response |
| P3 — Medium | SEV-3 | 1 hour response |
| P4 — Low | SEV-4 | Next business day |

**AI relevance:** Medium — useful for weighting search results (prefer resolutions from P1/P2 incidents over P4).

## Environment

**What it contains:** Which environment was affected.

**Operational value:** Distinguishes production incidents from staging noise.

**AI relevance:** High — always filter to `production` when retrieving incident resolution knowledge. Staging incidents rarely contain production-grade resolution steps.

**Expected values:** `production`, `staging`, `development`, `dr-site`

# Knowledge Extraction Rules

## High Value Fields (Always Index)

| Field | Reason |
|-------|--------|
| Summary | Primary semantic search target |
| Description | Contains symptoms, error messages, affected services |
| Resolution | Contains fix steps, root cause, verification |
| Components | Maps to services; enables scoped retrieval |
| Environment | Filters prod vs. non-prod |
| Priority | Weights result relevance |
| Labels (`recurring-issue`, `customer-impacting`) | Signals operational significance |
| Linked issues (relates to, caused by) | Builds incident correlation graph |
| Comments containing diagnostic commands or findings | Often contains resolution detail not in main fields |

## Medium Value Fields (Index Selectively)

| Field | Condition for Indexing |
|-------|----------------------|
| Labels (general) | Only if label is in the standardized label set |
| Assignee | Index only for "who resolved" context; useful for routing similar future issues |
| Fix Version | Index when it indicates a code change that resolved the issue |
| Sprint | Do not index unless tracking incident toil metrics |
| Attachments (text-based) | Index if they contain logs, config diffs, or architecture diagrams |
| Comments (general) | Index only comments >50 words that contain technical content |

## Low Value Fields (Do Not Index)

| Field | Reason |
|-------|--------|
| Reporter | Not operationally relevant for resolution retrieval |
| Created date / Updated date | Use for freshness ranking, not content indexing |
| Story points / Time tracking | Velocity metric, not operational knowledge |
| Watchers | Not relevant |
| Votes | Not relevant |
| Workflow transition timestamps | Internal process metadata |
| Attachment thumbnails / screenshots of dashboards | Low text value; prefer structured data |
| Comments like "acknowledged" or "+1" | No operational content |

# AI/RAG Indexing Guidance

## Index

These elements should be ingested into the LLM/RAG knowledge base:

1. **Resolution fields from closed INC tickets** — the primary knowledge source
2. **Description fields with structured symptoms** — enables symptom-to-resolution matching
3. **Comments containing diagnostic commands and their outputs** — often the most detailed troubleshooting record
4. **Root cause analysis sections** from PROB tickets
5. **Change request descriptions and outcomes** — documents what was changed and what broke
6. **Links between tickets** — builds a resolution correlation graph (e.g., INC-018 caused by CHG-042)
7. **Component + Environment + Priority** — as metadata facets for filtered retrieval
8. **Custom fields:** `root_cause_category`, `affected_customers_count`, `time_to_detect`, `time_to_resolve`

### Indexing Format

Each indexed ticket should produce a document with this structure:

```
TICKET: <project-key>-<number>
TITLE: <summary>
SERVICE: <component>
SEVERITY: <priority mapping>
ENVIRONMENT: <environment>
ROOT_CAUSE: <extracted from resolution or root cause field>
SYMPTOMS: <extracted from description>
RESOLUTION_STEPS: <extracted from resolution field>
RELATED_RUNBOOK: <linked wiki runbook if present>
RELATED_INCIDENTS: <linked issue keys>
DATE_RESOLVED: <resolution date>
```

## Do Not Index

1. **Internal process comments** — "Moving to backlog", "Bumping priority", "Assigning to sprint X"
2. **Automation-generated noise** — Bot comments from CI/CD, deployment notifications without diagnostic value
3. **PII and credentials** — Customer names, emails, API keys, tokens appearing in ticket bodies
4. **Staging/dev incidents** — Unless explicitly tagged `production-relevant`
5. **Tickets in status `Won't Fix` or `Duplicate`** — Resolution is not actionable
6. **Time-tracking and story point data** — Not operational knowledge
7. **Screenshots and images** — Unless OCR-processed and validated
8. **Tickets older than 18 months without `recurring-issue` label** — Likely outdated; infrastructure has changed

### PII Scrubbing Rules

Before indexing any Jira content:
- Strip email addresses matching `*@<customer-domain>`
- Redact API keys, tokens, and connection strings (regex: `(?:key|token|secret|password)\s*[:=]\s*\S+`)
- Replace customer names with `[CUSTOMER]` placeholder
- Preserve internal team member names (useful for "who knows this" queries)

# Resolution Quality Standards

Not all resolution fields are equally useful. Apply these quality gates before indexing:

| Quality Level | Criteria | Action |
|---------------|----------|--------|
| High (index immediately) | Contains root cause, specific commands/steps, verification, and links to post-mortem | Index as-is |
| Medium (index with flag) | Contains fix steps but missing root cause or verification | Index with `quality: medium` metadata; flag for enrichment |
| Low (do not index) | One-liner like "Fixed" or "Resolved by restart" with no detail | Skip — no retrieval value |
| Template-only | Contains only the ticket template with no filled content | Skip |

**Minimum resolution quality for indexing:**
- At least 3 sentences describing what was done
- At least one specific action (command, config change, rollback, or code fix)
- Identification of root cause or contributing factor

# Common Search Patterns

These are the query patterns the AI retrieval system should optimize for:

| Search Pattern | Jira Fields Used | Example Query |
|----------------|-----------------|---------------|
| Symptom → Resolution | Description (symptoms) → Resolution | "auth-service returning 503 after deploy" |
| Error message → Fix | Description + Comments (error text) → Resolution | "Fatal: could not decode JWT_SIGNING_KEY" |
| Service + Failure mode | Component + Labels → Resolution | "payment-service + database-lock" |
| Recurring issues | Labels (`recurring-issue`) + linked PROB tickets | "What keeps breaking in auth-service?" |
| Change impact | CHG tickets linked to INC tickets | "What change caused the outage on May 22?" |
| Similar past incidents | Summary + Component + Severity → full ticket | "Has this happened before?" |
| Escalation history | Comments with @mentions + status transitions | "Who was involved last time payment-service had a SEV-1?" |

# Integration Points

| System | Integration Type | Data Flow | Purpose |
|--------|-----------------|-----------|---------|
| PagerDuty | Webhook → Jira | Alert → creates INC ticket automatically | Incident creation |
| This Wiki (Obsidian) | Manual link | Jira ticket ↔ `[[INC-xxx-title]]` | Cross-reference resolution to post-mortem |
| Grafana | Link in Description | Dashboard URL embedded in ticket | Diagnostic context |
| GitHub / GitLab | PR link in ticket | Code change linked to INC or CHG | Maps fix to source |
| Slack (#incident-response) | Jira bot + manual | Status updates posted to channel | Communication |
| CI/CD Pipeline | Webhook | Deployment events create/update CHG tickets | Change tracking |
| RAG/LLM System | API pull (scheduled) | Closed INC tickets → knowledge base | Resolution retrieval |
| Confluence | Linked page | Post-mortem page linked from ticket | Detailed analysis |

### Data Sync Schedule (for RAG indexing)

| Sync Type | Frequency | Scope |
|-----------|-----------|-------|
| Full re-index | Weekly (Sunday 02:00 UTC) | All INC/PROB tickets resolved in last 18 months |
| Incremental sync | Every 4 hours | Tickets updated since last sync |
| Real-time push | On ticket close | Newly resolved INC tickets with priority P1/P2 |

# Governance Rules

1. **Every production incident MUST have a Jira ticket.** No incident is tracked only in Slack or PagerDuty.
2. **Resolution field MUST be populated before closing an INC ticket.** Tickets closed without resolution content are flagged in weekly governance audit.
3. **Post-mortem link MUST be added within 3 business days** for SEV-1 and SEV-2 incidents (per [[ESC-001-platform-wide-incident-escalation-rules]]).
4. **Component field MUST match the service catalog.** Freeform component creation is restricted to project admins.
5. **Labels MUST use the standardized set.** Non-standard labels are cleaned up in monthly audit.
6. **Change tickets MUST be linked to the INC ticket** if the change caused an incident.
7. **Problem tickets MUST link all related INC tickets** to build the recurrence graph.
8. **Tickets containing customer PII MUST be marked with `pii-present` label** and excluded from AI indexing until scrubbed.
9. **Tickets older than 18 months** are archived and removed from active RAG index unless tagged `evergreen`.
10. **Exception requests for guardrails** (see [[GR-001-database-migration-guardrails]]) MUST have a corresponding GOV ticket.

### Compliance Audit

| Check | Frequency | Owner | Action on Failure |
|-------|-----------|-------|-------------------|
| Resolution field populated on closed tickets | Weekly | SRE Leadership | Return ticket to "Resolved" status; notify assignee |
| Component field matches service catalog | Monthly | Platform team | Correct and notify team lead |
| Post-mortem linked for SEV-1/SEV-2 | Weekly | Incident Manager | Escalate to EM if overdue |
| PII label present where needed | Monthly | Security team | Scrub and flag |
| Stale tickets (no update >30 days, not closed) | Bi-weekly | Project leads | Close or re-assign |

# Escalation Considerations

When Jira data is used during active incident response:

1. **Do not rely solely on Jira search during a live SEV-1.** Jira search latency can be 5–15 seconds. The RAG system should have pre-indexed resolutions available for sub-second retrieval.
2. **Jira may be unavailable during an outage.** If Jira is down or degraded, responders should use the wiki (this vault) and Slack history as fallback. The RAG index operates independently of Jira uptime.
3. **Permissions may block access.** Some tickets (security incidents, HR-related) are restricted. The AI system must respect Jira permission schemes — do not index restricted-visibility tickets.
4. **Escalation path is documented in the ticket.** When the AI retrieves a past resolution, it should also surface the escalation path used (from Comments or linked escalation rules) so responders know who to contact if the same fix doesn't work.

# Known Limitations

| Limitation | Impact | Workaround |
|------------|--------|-----------|
| Jira full-text search is slow and imprecise | Responders can't quickly find past resolutions during incidents | RAG system provides pre-indexed, semantic search |
| Resolution field is unstructured free text | Inconsistent quality; hard to parse programmatically | Enforce resolution template via Jira workflow validator |
| No native link between Jira and Obsidian wiki | Manual cross-referencing required | Naming convention: `INC-<NNN>` in Jira maps to `[[INC-<NNN>-<slug>]]` in wiki |
| Attachments are not text-searchable | Log files and config dumps in attachments are invisible to search | Extract text from attachments during RAG sync; store as supplementary content |
| Label sprawl | Hundreds of unused or misspelled labels reduce signal | Monthly label audit; restrict creation to project admins |
| Jira Cloud rate limits (API) | Bulk extraction for RAG may hit throttling | Use pagination, respect `X-RateLimit` headers, schedule syncs during off-peak |
| Custom field IDs change between instances | Field mapping breaks during Jira migrations | Maintain a field mapping registry; validate after any Jira upgrade |
| Comments are chronological, not structured | Diagnostic gold is buried in comment threads | AI extraction should weight comments by length and technical keyword density |

# Related Documents

- [[ESC-001-platform-wide-incident-escalation-rules]] — Defines when and how to escalate; tickets track escalation history
- [[GR-001-database-migration-guardrails]] — Change tickets must reference guardrail compliance
- [[RB-005-database-timeout-connection-exhaustion]] — Runbook frequently linked from INC tickets as resolution reference
- [[RB-006-failed-deployment-rollback]] — Rollback procedures documented here; CHG tickets reference this
- [[RB-007-pod-crash-investigation]] — Diagnostic steps that appear in INC ticket descriptions
- Incident Template — [[Incident Template]] — Wiki post-mortem structure that mirrors Jira INC ticket content
- KB Article Template — [[KB Article Template]] — Distilled knowledge extracted from resolved Jira tickets

# Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-12 | SRE Leadership | Initial publication |
