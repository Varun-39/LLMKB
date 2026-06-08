---
title: Production Support Wiki
tags:
  - homepage
  - production-support
created: 2026-06-02
updated: 2026-06-02
type: homepage
---

# 🏠 Production Support Wiki

> The single source of truth for production support operations — incidents, runbooks, knowledge base articles, vendor advisories, and operational policies, all structured for fast retrieval during on-call rotations.

---

## 📊 At a Glance

| Metric | Count |
|--------|-------|
| Active Incidents | `$= dv.pages('"Incidents/Active"').where(p => p.status == "active" || p.status == "investigating").length` |
| Total Incidents | `$= dv.pages('"Incidents"').where(p => p.id && dv.func.startswith(p.id, "INC")).length` |
| Runbooks | `$= dv.pages('"Runbooks"').where(p => p.id).length` |
| KB Articles | `$= dv.pages('"KB"').where(p => p.id).length` |

---

## 🧭 Navigation

| Section | Purpose |
|---------|---------|
| [[Incident Index]] | All incidents — sortable Dataview tables by severity, status, and category |
| [[Runbook Index]] | Step-by-step operational procedures for known failure scenarios |
| [[Category Navigation]] | Browse incidents and runbooks by problem type or service |
| [[Cross-Link Map]] | Incident clusters, runbook coverage map, and backlink graph |

---

## 🚦 Quick Links

- 🚨 **[[Incident Index]]** — Full incident table, filter by severity and status
- 📋 **[[Runbook Index]]** — Find the right runbook fast
- 🗂️ **[[Category Navigation]]** — Browse by Kubernetes / Database / Deployment / Infra
- 🔗 **[[Cross-Link Map]]** — Recurring patterns and runbook coverage gaps
- 📝 **Templates** — Start a new note from a standard template (see `Templates/`)

---

## 📁 Vault Structure

| Folder | Contents | ID Prefix |
|--------|----------|-----------|
| `00-Home/` | Homepage, setup guides, conventions | — |
| `Incidents/` | Incident records (Active / Resolved) | `INC-` |
| `Runbooks/` | Operational procedures | `RB-` |
| `KB/` | Knowledge base articles | `KB-` |
| `Vendors/` | Vendor advisories and notes | `VN-` |
| `Policies/Guardrails/` | Operational rules and constraints | `GR-` |
| `Policies/Escalation/` | Escalation matrices and contacts | `ESC-` |
| `Policies/Standards/` | Metadata and naming standards | `META-` |
| `Indexes/` | Dataview dashboards and navigation | — |
| `Templates/` | Reusable note templates | — |
| `Tests/` | QA checklists and test scenarios | — |
| `Assets/` | Diagrams and screenshots | — |

---

## 🎯 Guiding Principles

1. **Document everything** — every incident gets a record, no matter how small.
2. **Runbooks are living documents** — update them after every use.
3. **Metadata is mandatory** — consistent YAML frontmatter keeps Dataview queries accurate.
4. **Link generously** — use `[[wikilinks]]` to connect incidents, runbooks, and services.
5. **One source of truth** — if it's not in the wiki, it didn't happen.

---

## 🕒 Recently Modified

```dataview
TABLE WITHOUT ID
  file.link AS "Note",
  file.folder AS "Location",
  file.mtime AS "Last Modified"
FROM "" 
WHERE file.name != "Production Support Wiki"
SORT file.mtime DESC
LIMIT 8
```

---

## 🚀 Getting Started

New to this wiki? Follow these steps:

1. **Set up Obsidian** — install the Dataview plugin (see [[Plugin Setup Guide]])
2. **Learn the conventions** — read the [[Conventions and Usage Guide]] for naming, tagging, and metadata standards
3. **Create notes from templates** — use the scaffolding in `Templates/` for consistency
4. **Tag and link** — apply metadata and `[[wikilinks]]` so your notes are queryable and navigable

---

## 📚 Reference Documents

- [[Plugin Setup Guide]] — Required and recommended Obsidian plugins
- [[Conventions and Usage Guide]] — Metadata schema, naming, tagging, and Dataview rules
