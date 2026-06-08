---
title: Day 2 - Conventions and Usage Guide
tags:
  - meta
  - conventions
  - standards
created: 2026-06-02
updated: 2026-06-02
type: reference
---

## Overview

Standards for metadata, naming, tagging, and Obsidian usage in this vault. Follow these to keep all notes queryable via Dataview and navigable via wikilinks.

---

## 1. Metadata Schema

### Incident Frontmatter

```yaml
id: INC-<NNN>
title: <short title>
severity: SEV-1|SEV-2|SEV-3|SEV-4
service: <service-name>           # lowercase, hyphenated
environment: prod|staging|dev
category: outage|degradation|security|data-loss|deployment-failure
status: active|investigating|mitigated|resolved
owner: <name>
assigned-to: <name>
date: YYYY-MM-DD                  # when incident occurred
duration: <e.g. 47 minutes>
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [incident, ...]
related_runbooks:
  - "[[RB-xxx]]"
related_incidents:
  - "[[INC-xxx]]"
```

### Runbook Frontmatter

```yaml
id: RB-<NNN>
title: <short title>
service: <service-name>
severity: SEV-1|SEV-2|SEV-3|SEV-4
environment: prod|staging|dev
category: resource-exhaustion|connectivity|deployment|security|performance
status: active|deprecated|under-review
owner: <name>
created: YYYY-MM-DD
updated: YYYY-MM-DD
last-updated: YYYY-MM-DD
tags: [runbook, ...]
related_incidents:
  - "[[INC-xxx]]"
related_runbooks:
  - "[[RB-xxx]]"
```

### Dataview Rules

- Dates must be `YYYY-MM-DD` (unquoted) for Dataview date parsing
- Tags use inline YAML array: `[runbook, kubernetes, memory]`
- Wikilinks in frontmatter must be quoted: `"[[RB-001-title]]"`
- Avoid nested objects — keep fields flat for TABLE queries
- Hyphenated field names (e.g., `assigned-to`) work as-is in Dataview columns

---

## 2. Naming Convention

### Incidents

```
INC-<NNN>-<kebab-case-title>.md
```

- 3-digit zero-padded sequence: `001`, `002`, `003`
- Max 5 words in title
- Location: `Incidents/Active/` → move to `Incidents/Resolved/` on close

**Examples:**
- `INC-001-payment-service-oom-crash.md`
- `INC-002-database-connection-timeout.md`
- `INC-003-disk-full-logging-node.md`
- `INC-004-high-cpu-api-gateway.md`
- `INC-005-failed-deployment-auth-service.md`

### Runbooks

```
RB-<NNN>-<service>-<issue-type>.md
```

- 3-digit zero-padded sequence
- Service first, then issue type
- Location: `Runbooks/`

**Examples:**
- `RB-001-payment-gateway-oom-recovery.md`
- `RB-002-auth-service-token-rotation.md`
- `RB-003-postgres-connection-pool-exhaustion.md`
- `RB-004-kubernetes-pod-crashloop-generic.md`
- `RB-005-redis-cache-eviction-storm.md`

---

## 3. Tagging Convention

Apply tags in both the YAML `tags` field (Dataview) and inline at note bottom (graph view).

### Taxonomy

| Category | Tags |
|----------|------|
| **Technology** | `kubernetes`, `docker`, `aws`, `postgres`, `redis`, `kafka`, `nginx`, `java`, `python`, `node` |
| **Issue Type** | `memory`, `oom`, `cpu`, `disk`, `network`, `timeout`, `crashloop`, `deployment`, `connection-pool`, `certificate` |
| **Severity** | `critical` (SEV-1), `high` (SEV-2), `medium` (SEV-3), `low` (SEV-4) |
| **Environment** | `prod`, `staging`, `dev` |
| **Service Area** | `payments`, `auth`, `api`, `database`, `messaging`, `cdn`, `monitoring` |
| **Note Type** | `incident`, `runbook`, `index`, `template`, `postmortem` |
| **Urgency** | `immediate`, `next-sprint`, `backlog` |

### Rules

1. Every note requires at minimum: note type + technology + environment
2. Incidents must include a severity tag
3. Prefer specific over generic (`oom` + `memory`, not just `memory`)
4. All tags lowercase, hyphenated
5. New tags must be added to this taxonomy before use

---

## 4. Obsidian Usage

### Wikilinks

- Every incident links to its runbook: `[[RB-001-payment-gateway-oom-recovery]]`
- Every runbook links back to incidents: `[[INC-001-payment-service-oom-crash]]`
- Use `related_runbooks` / `related_incidents` frontmatter for Dataview; use inline links for narrative context

### Folder Rules

| Type | Location |
|------|----------|
| Active incidents | `Incidents/Active/` |
| Resolved incidents | `Incidents/Resolved/` |
| Runbooks | `Runbooks/` |
| Templates | `Templates/` |
| Indexes | `Indexes/` |
| Tests | `Tests/` |
| Assets | `Assets/` |

Moving a file between folders does not break wikilinks (Obsidian resolves by filename).

### Template Workflow

1. Create new file in correct folder with proper naming convention
2. Command Palette → "Insert template" → select Incident or Runbook template
3. Replace all `<placeholder>` values
4. Add wikilinks to related notes
5. Confirm note surfaces in relevant Dataview index

### Dataview Queries (Ready to Use)

**Active incidents:**
```dataview
TABLE severity, service, assigned-to, date
FROM "Incidents/Active"
SORT date DESC
```

**Runbooks by service:**
```dataview
TABLE title, owner, last-updated
FROM "Runbooks"
WHERE service = "payment-gateway"
SORT last-updated DESC
```

**SEV-1 incidents this month:**
```dataview
TABLE title, service, duration
FROM "Incidents"
WHERE severity = "SEV-1" AND date >= date(2026-06-01)
SORT date DESC
```

### Graph View

- Filter by tag to isolate clusters (e.g., only `#payments` nodes)
- Orphan notes = documentation gaps — every note should have at least one backlink
