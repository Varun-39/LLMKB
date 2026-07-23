---
id: JIRA-OPS-4903
title: "ReportingDB connection pool exhausted during nightly export job"
source: jira
source_key: OPS-4903
service: reporting-service
severity: SEV-2
status: "Done"
resolution: "Fixed"
tags:
  - imported
  - jira
date: 2026-07-21
imported_at: 2026-07-23T13:03:10.343009+00:00
review_status: pending
---

## Summary

HikariPool-1 timed out acquiring a connection during ExportJobExecutor.runExport. Pool size was too small for the nightly export job's concurrency.

## Jira Comments

- **on-call** (2026-07-21): Increased HikariCP maximumPoolSize from 10 to 25 and added a queue timeout. Export job re-run succeeded.
