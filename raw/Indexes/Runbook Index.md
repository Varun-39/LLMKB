---
title: "Runbook Index"
tags: [index, runbooks]
created: 2026-06-02
type: index
---

## Runbook Index

This index lists all operational runbooks in the vault. Runbooks provide step-by-step procedures for handling known failure scenarios, routine maintenance tasks, and escalation paths. They live in the `Runbooks/` folder and must include frontmatter with `service`, `last-updated`, and `owner` fields.

### Conventions

- **Naming format:** `RB-ServiceName-IssueName.md`
  - Examples: `RB-PaymentGateway-TimeoutRecovery.md`, `RB-AuthService-TokenRotation.md`
- **Ownership:** Every runbook has a single `owner` — the engineer responsible for keeping it current
- **Review cadence:** Runbooks should be reviewed after every use and at minimum quarterly
- **Scope:** One runbook per failure scenario. If a procedure branches significantly, split it into separate runbooks and cross-link them.

---

## All Runbooks

```dataview
TABLE title AS "Runbook", service AS "Service", last-updated AS "Last Updated", owner AS "Owner"
FROM "Runbooks"
SORT last-updated DESC
```

---

## Runbooks by Service

> Organize runbooks by the service or system they apply to. Add entries as runbooks are created.

| Service | Runbooks |
|---------|----------|
| Payment Gateway | *None yet* |
| Auth Service | *None yet* |
| Database (Primary) | *None yet* |
| Message Queue | *None yet* |
| CDN / Edge | *None yet* |

---

## Creating a New Runbook

1. Navigate to `Runbooks/`
2. Create a new note using the naming convention: `RB-ServiceName-IssueName.md`
3. Apply the **Runbook Template** from `Templates/`
4. Fill in all frontmatter fields:
   - `title` — Human-readable name of the procedure
   - `service` — The system/service this runbook applies to
   - `last-updated` — Date of last meaningful edit (YYYY-MM-DD)
   - `owner` — Engineer responsible for this runbook
   - `tags` — Include `runbook` plus service-specific tags
5. Write clear, numbered steps that an on-call engineer can follow at 3 AM under pressure
6. Include rollback steps and escalation contacts where applicable
