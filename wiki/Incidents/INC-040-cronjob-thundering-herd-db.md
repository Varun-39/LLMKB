---
id: INC-040
title: CronJob Thundering Herd — All Batch Jobs Hit DB Simultaneously
severity: SEV-2
service: postgres-primary
environment: prod
category: degradation
date: 2026-03-22
duration: "18m"
tags:
  - incident
  - cronjob
  - database
  - thundering-herd
  - scheduling
  - high
  - prod
---

## Summary

At 00:00 UTC on 2026-03-22, 14 Kubernetes CronJobs all scheduled at midnight fired simultaneously, creating 14 parallel batch processes each opening 20 database connections. The 280 simultaneous connections exhausted the Postgres connection pool (max_connections=300), causing all interactive services to timeout on DB operations for 18 minutes.

## Symptoms

- PagerDuty: `DB-ConnectionPoolExhausted` at 00:03 UTC
- pg_stat_activity: 298/300 connections active
- auth-service, payment-service: `Connection is not available, request timed out after 30000ms`
- All midnight CronJobs running simultaneously
- API error rate: 35% (all DB-dependent endpoints)

## Diagnosis

1. Connection count at max
   ```bash
   psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
   # 298
   psql -U postgres -c "SELECT application_name, count(*) FROM pg_stat_activity GROUP BY 1 ORDER BY 2 DESC;"
   # batch-reports: 42, batch-cleanup: 38, batch-analytics: 35, ...
   ```

2. All CronJobs scheduled at `0 0 * * *` (midnight)
   ```bash
   kubectl get cronjobs --all-namespaces -o custom-columns=NAME:.metadata.name,SCHEDULE:.spec.schedule | grep "0 0"
   # 14 jobs all at "0 0 * * *"
   ```

## Resolution

1. **Mitigate:** Suspended non-critical CronJobs immediately
   ```bash
   kubectl patch cronjob batch-analytics -n analytics -p '{"spec":{"suspend":true}}'
   kubectl patch cronjob batch-reports -n reporting -p '{"spec":{"suspend":true}}'
   # Repeated for 10 non-critical jobs
   ```

2. **Fix:** Staggered CronJob schedules across the hour (0, 5, 10, 15 min offsets)

3. **Verify:** Connection count dropped to 85 within 2 minutes of suspending jobs

## Post-Incident Review

- 14 CronJobs all defaulted to midnight without coordination
- Added scheduling policy: no more than 3 batch jobs in any 5-minute window
- Set `concurrencyPolicy: Forbid` on all CronJobs to prevent overlap
- Added PgBouncer between batch jobs and Postgres to limit connection count

## Links

- Runbooks: [[RB-005-database-timeout-connection-exhaustion]]
- Related incidents: [[INC-009-db-connection-pool-exhausted]]
