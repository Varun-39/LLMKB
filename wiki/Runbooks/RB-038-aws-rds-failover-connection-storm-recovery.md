---
id: RB-038
title: AWS RDS Failover Connection Storm Recovery
service: payment-service
related_services:
  - auth-service
  - reporting-service
  - postgres-primary
severity: SEV-1
environment: prod
category: connectivity
risk_level: high
estimated_duration: "25m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - rds
  - aws
  - failover
  - connection-storm
  - database
  - prod
---

## Purpose

Recover application services after an AWS RDS Multi-AZ failover triggers a connection storm that exhausts `max_connections` on the new primary, preventing normal service recovery.

**Desired outcome:** Application services reconnected to new RDS primary with stable connection count within limits, request error rate back to baseline.

## Success Criteria

- `pg_stat_activity` connection count within safe bounds (< 80% of `max_connections`)
- Application pods Running and serving requests
- Error rate < 1% for 15 consecutive minutes
- No `FATAL: remaining connection slots are reserved` errors in application logs

## Scope

| Attribute | Value |
|-----------|-------|
| Service | payment-service (primary), any service with direct RDS connections |
| Related services | auth-service, reporting-service |
| Environments | prod |
| Use when | RDS failover event followed by application connection errors / OOMKilled pods |
| Do NOT use when | RDS is still failing over (wait for failover to complete first) |
| Risk level | High — killing DB connections impacts active requests |
| Estimated duration | 20–25 minutes |
| Approval required | No (emergency) |

## Prerequisites

- [ ] Confirm RDS failover is complete (AWS console or `aws rds describe-events`)
- [ ] `psql` access to new RDS primary
- [ ] `kubectl` access to affected namespaces
- [ ] Know application's connection pool settings (`max_pool_size`, `min_pool_size`)

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `psql` | Kill idle connections, monitor pg_stat_activity | Superuser |
| `kubectl` | Staged pod restart | Namespace admin |
| AWS CLI | Confirm RDS failover status | Read access |
| Grafana | Monitor connection count and error rate | Read access |

## Trigger

- AWS event: `Multi-AZ failover completed`
- Alert: `payment-service error rate > 5%` or `database max_connections exhausted`
- Symptom: Application pods OOMKilling during reconnection storm

## Triage

1. Confirm RDS failover is complete:
   ```bash
   aws rds describe-events --source-type db-instance --duration 60 \
     --source-identifier <db-instance-id>
   # Look for: "Multi-AZ failover completed"
   ```
2. Check connection state on new primary:
   ```bash
   psql -h <new-rds-endpoint> -U admin -c \
     "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"
   # idle: high number = connection storm in progress
   ```
3. Wrong runbook? If RDS is still failing over, wait — do not touch connections yet.

## Investigation

1. **Check if max_connections is exhausted**
   ```bash
   psql -h <rds-endpoint> -U admin -c \
     "SELECT count(*) FROM pg_stat_activity; SHOW max_connections;"
   # What to look for: count close to max_connections
   ```
2. **Identify which application is flooding connections**
   ```bash
   psql -h <rds-endpoint> -U admin -c \
     "SELECT application_name, count(*), state FROM pg_stat_activity GROUP BY 1,3 ORDER BY 2 DESC;"
   ```
3. **Check if pods are in OOMKilled restart loop**
   ```bash
   kubectl get pods -n <namespace> | grep -E "OOMKilled|CrashLoop"
   ```
4. **Decision point:**
   - IF connections at max_connections → Option A (kill idle) then Option B (staged restart)
   - IF pods OOMKilling before connecting → Option B first
   - IF connections within limits but errors persist → Option C (verify endpoint)

## Mitigation

### Option A: Kill idle connections to free slots

```bash
psql -h <rds-endpoint> -U admin -c \
  "SELECT pg_terminate_backend(pid) 
   FROM pg_stat_activity 
   WHERE state='idle' AND application_name='<app-name>';"
```

### Option B: Staged pod restart (avoid new storm)

```bash
# Slow restart — 1 pod at a time with a gap
kubectl patch deployment <app> -n <namespace> \
  -p '{"spec":{"strategy":{"rollingUpdate":{"maxSurge":1,"maxUnavailable":0}}}}'
kubectl rollout restart deployment/<app> -n <namespace>
# Watch pod startup pace:
watch kubectl get pods -n <namespace>
```

### Option C: Verify application is pointing to new RDS endpoint

```bash
# RDS endpoint DNS auto-updates after failover, but cached connections may point to old IP
kubectl exec -n <namespace> deploy/<app> -- nslookup <rds-endpoint>
# Compare IP vs aws rds describe-db-instances output
```

**After mitigation:** Monitor connection count for 10 minutes before declaring stable.

## Verification

- [ ] `pg_stat_activity` count < 80% of `max_connections`
- [ ] Application pods Running and Ready
- [ ] Error rate < 1% for 15 minutes
- [ ] No OOMKilled pods

```bash
psql -h <rds-endpoint> -U admin -c \
  "SELECT count(*) FROM pg_stat_activity WHERE application_name='<app-name>';"
# Expected: within pool size bounds
```

## Failure Signals

- Connection count climbs back to max immediately after killing idle connections (retry storm continuing)
- Pods OOMKilling faster than Kubernetes can restart them
- RDS endpoint DNS not resolving to new primary (DNS propagation lag)

## Rollback

- No rollback for connection storm recovery — if staged restart makes things worse:
  1. Scale deployment to 0: `kubectl scale deployment/<app> -n <namespace> --replicas=0`
  2. Kill all connections from that app in pg_stat_activity
  3. Scale back up to 1 replica, monitor, then 2, then full count

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| max_connections exhausted and apps OOMKilling | DBA Lead + SRE | #incident-response | Immediate |
| RDS secondary also failing | AWS support + Platform Lead | #incident-response | Immediate |
| Recovery taking > 20 min | Senior on-call | PagerDuty | 5 min |

## Notes

- **Root cause fix (long-term):** Add pgBouncer or RDS Proxy in front of RDS to absorb reconnect storms.
- **Connection pool sizing rule:** `max_pool_size = max_connections / (num_pods * 1.2)`.
- After this incident, consider enabling exponential backoff with jitter in application DB reconnect logic.
- See [[INC-083-aws-rds-failover-connection-storm]] for the incident that motivated this runbook.

## Maintenance

- **Last tested:** 2026-05-11
- **Review cycle:** Quarterly
- **Next review:** 2026-08-11
- **Test method:** Simulate RDS failover in staging, observe connection storm, execute runbook.

## last Updated

| Date | Author | Change |
|------|--------|--------|
| 2026-05-11 | DBA Team + SRE | Initial publication |
