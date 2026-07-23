---
id: JIRA-OPS-4821
title: "PaymentService pods OOMKilled after v2.14.0 rollout"
source: jira
source_key: OPS-4821
service: payment-gateway
severity: SEV-1
status: "Done"
resolution: "Fixed"
tags:
  - imported
  - jira
date: 2026-06-02
imported_at: 2026-07-23T13:03:10.342670+00:00
review_status: pending
---

## Summary

All payment-gateway pods OOMKilled in prod. Root cause: unbounded idempotency cache introduced in v2.14.0.

## Jira Comments

- **Priya Sharma** (2026-06-02): Cherry-picked cache eviction patch (PR #1847), bumped memory limit to 2Gi as a stopgap, rolled out v2.14.1-hotfix.
- **Priya Sharma** (2026-06-02): Confirmed all pods healthy, 0 restarts. Closing.
