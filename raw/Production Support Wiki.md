---
title: "Production Support Wiki"
tags: [homepage, production-support]
created: 2026-06-02
type: homepage
---
``
## Welcome to the Production Support Wiki

This vault is the single source of truth for our production support operations. It houses incident records, runbooks, post-mortem analyses, test scenarios, and operational dashboards — all structured for fast retrieval during on-call rotations and incident response.

**Guiding principles:**
- Every incident gets documented, no matter how small
- Runbooks are living documents — update them after every use
- Use tags and frontmatter consistently so Dataview queries stay accurate

---

## Navigation

| Section | Description |
|---------|-------------|
| [[Incident Index]] | All incidents — table view with Dataview, by severity and category |
| [[Runbook Index]] | Standard operating procedures for known failure scenarios |
| [[Category Navigation]] | Browse incidents and runbooks by problem type or service |
| [[Cross-Link Map]] | Incident clusters, runbook coverage map, and backlink graph |
| [[Templates]] | Reusable templates for incidents, runbooks, and post-mortems |
| [[Tests]] | Test scenarios and validation checklists |
| [[Assets]] | Diagrams, screenshots, and architecture visuals |

---

## Quick Links

- 🚨 [[Incident Index]] — Full incident table, filter by severity and status
- 📋 [[Runbook Index]] — Find the right runbook fast
- 🗂️ [[Category Navigation]] — Browse by Kubernetes / DB / Deployment / Infra
- 🔗 [[Cross-Link Map]] — Recurring patterns and runbook coverage gaps
- 📝 [[Templates]] — Start a new incident or runbook from a template

---

## Recently Modified Notes

```dataview
TABLE file.mtime AS "Last Modified", tags AS "Tags"
FROM ""
SORT file.mtime DESC
LIMIT 5
```

---

## Getting Started

1. Install required plugins (see the [[Plugin Setup Guide]] or the Day 1 checklist)
2. Use templates from the `Templates/` folder when creating new notes
3. Tag every note with appropriate metadata in the YAML frontmatter
4. Use `[[wikilinks]]` to connect related incidents, runbooks, and services
