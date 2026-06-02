---
title: Incident Index
tags:
  - index
  - incidents
created: 2026-06-02
updated: 2026-06-02
type: index
---

## Incident Index

Central view of all incidents in the vault. Incidents live in `Incidents/Active/` and `Incidents/Resolved/`. Add new incidents using the template in `Templates/Incident Template.md`.

**Naming convention:** `INC-<NNN>-<short-kebab-title>.md`
**Severity:** SEV-1 = critical customer impact · SEV-2 = degraded · SEV-3 = internal · SEV-4 = informational

---

## All Incidents

```dataview
TABLE
  title AS "Title",
  severity AS "Sev",
  service AS "Service",
  status AS "Status",
  date AS "Date",
  duration AS "Duration",
  owner AS "Owner"
FROM "Incidents"
SORT date DESC
```

---

## Active / Investigating

```dataview
TABLE
  title AS "Title",
  severity AS "Sev",
  service AS "Service",
  assigned-to AS "Assigned",
  date AS "Date"
FROM "Incidents/Active"
WHERE status = "active" OR status = "investigating"
SORT severity ASC, date DESC
```

---

## SEV-1 Incidents

```dataview
TABLE
  title AS "Title",
  service AS "Service",
  status AS "Status",
  date AS "Date",
  duration AS "Duration"
FROM "Incidents"
WHERE severity = "SEV-1"
SORT date DESC
```

---

## By Category

### Kubernetes / Container

```dataview
TABLE title AS "Title", severity AS "Sev", service AS "Service", date AS "Date"
FROM "Incidents"
WHERE contains(tags, "kubernetes") OR contains(tags, "container")
SORT date DESC
```

### Infrastructure / Resource

```dataview
TABLE title AS "Title", severity AS "Sev", service AS "Service", date AS "Date"
FROM "Incidents"
WHERE contains(tags, "disk") OR contains(tags, "cpu") OR contains(tags, "infra") OR contains(tags, "memory")
SORT date DESC
```

### Database

```dataview
TABLE title AS "Title", severity AS "Sev", service AS "Service", date AS "Date"
FROM "Incidents"
WHERE contains(tags, "database") OR contains(tags, "postgres")
SORT date DESC
```

### Deployment / Application

```dataview
TABLE title AS "Title", severity AS "Sev", service AS "Service", date AS "Date"
FROM "Incidents"
WHERE contains(tags, "deployment") OR contains(tags, "config") OR contains(tags, "feature-flag")
SORT date DESC
```

---

## Adding a New Incident

1. Create file in `Incidents/Active/` — name: `INC-<NNN>-<short-title>.md`
2. Insert template: Command Palette → "Insert template" → `Incident Template`
3. Fill all YAML frontmatter fields, especially `id`, `severity`, `status`, `date`, `tags`
4. Link related runbooks in `related_runbooks` frontmatter
5. Add inline `[[wikilinks]]` to related incidents in the note body
6. Move to `Incidents/Resolved/` when `status: resolved`
