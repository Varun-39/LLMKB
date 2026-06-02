---
title: "Plugin Setup Guide"
tags: [meta, setup]
created: 2026-06-02
type: reference
---

## Plugin Setup Guide — Day 1

Install and configure these plugins before adding any content to the vault.

---

### Required Plugins

#### 1. Templates (Core)

- **Source:** Core plugin (Settings → Core Plugins → toggle on)
- **Why:** Provides consistent starting points for incident reports, runbooks, and post-mortems so on-call engineers don't waste time formatting under pressure.
- **Critical setting:** Set "Template folder location" to `Templates` in Settings → Core Plugins → Templates → Options.

#### 2. Dataview (Community)

- **Source:** Community Plugins → Browse → search "Dataview"
- **Why:** Enables live TABLE/LIST queries across the vault using frontmatter fields, powering all index dashboards and the homepage feed.
- **Critical setting:** Enable "Enable JavaScript Queries" in Dataview settings (needed for advanced dashboard blocks later). Also ensure "Enable Inline Queries" is on.

---

### Recommended Additional Plugins

#### 3. Templater (Community)

- **Source:** Community Plugins → Browse → search "Templater"
- **Why:** Extends core Templates with dynamic variables (auto-fill dates, prompt for severity on creation, auto-generate file names based on naming conventions like `RB-ServiceName-IssueName`).
- **Critical setting:** Set "Template folder location" to `Templates` and enable "Trigger Templater on new file creation."

#### 4. Calendar (Community)

- **Source:** Community Plugins → Browse → search "Calendar"
- **Why:** Provides a visual calendar sidebar that integrates with daily notes — useful for correlating incidents with dates and tracking on-call shift handovers.
- **Critical setting:** Set "Weekly note format" and enable "Show week numbers" if your on-call rotations are weekly.

---

### Post-Install Checklist

- [ ] Core Templates plugin enabled and pointed at `Templates/`
- [ ] Dataview installed, inline queries enabled
- [ ] Templater installed and configured (optional but recommended)
- [ ] Calendar installed (optional but recommended)
- [ ] Verified Dataview queries render on [[Production Support Wiki]] homepage
