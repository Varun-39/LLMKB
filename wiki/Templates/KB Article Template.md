---
id: KB-<NNN>
title: <concise-article-title>
service: <service-name|platform-wide>
category: <how-to|troubleshooting|reference|architecture|faq>
audience: <l1-support|l2-sre|developers|all>
status: <published|draft|under-review|deprecated>
owner: <author-name>
reviewer: <reviewer-name>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
last_validated: <YYYY-MM-DD — when someone last confirmed this still works>
expires: <YYYY-MM-DD or never>
tags:
  - kb
  - <technology>
  - <topic>
  - <environment>
related_incidents:
  - "[[INC-xxx-title]]"
related_runbooks:
  - "[[RB-xxx-title]]"
related_kb:
  - "[[KB-xxx-title]]"
superseded_by:
  - "[[KB-xxx-title]]"
---

## TL;DR

<Two-line answer for L1 support. State the fix in the fewest words possible. Full detail follows below.>

## Problem Statement

<Clear, one-paragraph description of the problem or question this article answers. Write for someone encountering this issue for the first time.>

## Applies To

| Attribute | Value |
|-----------|-------|
| Service(s) | <service-name> |
| Environment(s) | <prod, staging, dev> |
| Version(s) | <app version or "all"> |
| Platform | <Kubernetes, AWS, bare-metal> |

## Prerequisites

- <Required access, permissions, or tools to apply this solution>
- <Specific tool versions if relevant>

## Root Cause / Explanation

<Technical explanation of why this happens. Keep it factual and concise. Include diagrams or architecture references if helpful.>

## Solution

### Temporary Workaround (if a permanent fix is not yet available)

<Immediate steps to restore service. State clearly that this is temporary and what it depends on, e.g. "until patch X ships".>

### Permanent Fix

#### Option A: <primary-solution>

1. <Step>
   ```bash
   <command>
   ```
2. <Step — prose or a code block as needed>
3. <Step>

#### Option B: <alternative-solution> (if applicable)

1. <Step>
2. <Step>

## Verification

- [ ] <How to confirm the solution worked>
- [ ] <Expected state after fix>

## Known Limitations

- <Edge case or situation where this solution does not apply>
- <Version-specific behavior>

## References

- [[RB-xxx-title]] — Related runbook
- [[INC-xxx-title]] — Incident where this was discovered
- <External link or vendor doc URL>

## Revision History

| Date | Author | Change |
|------|--------|--------|
| <YYYY-MM-DD> | <name> | Initial publication |
