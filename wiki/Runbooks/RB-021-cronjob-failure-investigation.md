---
id: RB-021
title: CronJob Failure Investigation and Recovery
service: "*"
related_services:
  - batch-processing
  - reporting-service
  - analytics-service
severity: SEV-3
environment: prod
category: deployment
risk_level: low
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - cronjob
  - kubernetes
  - batch
  - scheduling
  - prod
related_incidents:
  - "[[INC-040-cronjob-thundering-herd-db]]"
related_runbooks:
  - "[[RB-007-pod-crash-investigation]]"
  - "[[RB-005-database-timeout-connection-exhaustion]]"
related_guardrails: []
---

## Purpose

Diagnose and recover from Kubernetes CronJob failures including missed schedules, stuck jobs, resource contention, and thundering herd problems.

**Desired outcome:** CronJob completing successfully on schedule, no missed executions, no resource contention with production workloads.

## Success Criteria

- CronJob last successful run within expected schedule window
- Job pod completed with exit code 0
- No resource contention caused by batch jobs
- No overlapping job runs (if concurrencyPolicy=Forbid)

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any Kubernetes CronJob |
| Related services | batch-processing, reporting-service, analytics-service |
| Environments | prod, staging |
| Use when | CronJob not running, failing, or causing resource contention |
| Do NOT use when | One-off Job failure (check pod logs directly) |
| Risk level | Low |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to affected namespace
- [ ] Knowledge of which CronJob is failing
- [ ] Access to job execution logs

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | CronJob and Job inspection | Cluster admin |
| Grafana | Resource utilization during job runs | Read access |

## Trigger

- Alert: `*-CronJobMissed`, `*-CronJobFailed`
- Symptom: Expected batch output not generated (reports missing, data not synced)
- Symptom: CronJob pods in Error or OOMKilled state
- Metric: Job completion time trending upward

## Triage

1. Check CronJob status
   ```bash
   kubectl get cronjob <name> -n <namespace>
   # What to look for: LAST SCHEDULE, ACTIVE, SUSPEND
   ```

2. Check recent Job history
   ```bash
   kubectl get jobs -n <namespace> --sort-by='.status.startTime' | grep <cronjob-name> | tail -5
   # What to look for: COMPLETIONS (1/1 = success, 0/1 = failed)
   ```

3. Check failed pod logs
   ```bash
   kubectl get pods -n <namespace> --sort-by='.status.startTime' | grep <cronjob-name> | tail -3
   kubectl logs <failed-pod> -n <namespace>
   ```

## Investigation

1. **Check if CronJob is suspended**
   ```bash
   kubectl get cronjob <name> -n <namespace> -o jsonpath='{.spec.suspend}'
   # true = suspended, won't run
   ```

2. **Check for missed schedules (startingDeadlineSeconds exceeded)**
   ```bash
   kubectl describe cronjob <name> -n <namespace> | grep -A5 "Events"
   # What to look for: "Cannot determine if job needs to be started"
   ```

3. **Check concurrencyPolicy**
   ```bash
   kubectl get cronjob <name> -n <namespace> -o jsonpath='{.spec.concurrencyPolicy}'
   # Forbid = won't start if previous still running
   # Allow = can overlap (resource danger)
   ```

4. **Check if job pods are stuck or consuming too many resources**
   ```bash
   kubectl get pods -n <namespace> -l job-name=<job-name> --field-selector=status.phase!=Succeeded
   kubectl top pods -n <namespace> -l job-name=<job-name>
   ```

5. **Decision point:**
   - IF suspended → proceed to Mitigation Option A
   - IF failed with error → proceed to Mitigation Option B
   - IF missed due to overlap → proceed to Mitigation Option C
   - IF resource contention → proceed to Mitigation Option D

## Mitigation

### Option A: Unsuspend CronJob

```bash
kubectl patch cronjob <name> -n <namespace> -p '{"spec":{"suspend":false}}'
```

### Option B: Fix failed job and re-trigger

```bash
# Fix underlying issue (env var, image, permissions), then trigger manually:
kubectl create job <cronjob-name>-manual --from=cronjob/<cronjob-name> -n <namespace>
```

### Option C: Clear stuck job blocking new runs

```bash
kubectl delete job <stuck-job-name> -n <namespace>
# New CronJob run will trigger on next schedule
```

### Option D: Add resource limits and stagger schedules

```bash
# Add resource limits to prevent node starvation:
kubectl patch cronjob <name> -n <namespace> --type='json' \
  -p='[{"op":"add","path":"/spec/jobTemplate/spec/template/spec/containers/0/resources","value":{"limits":{"cpu":"2","memory":"2Gi"},"requests":{"cpu":"500m","memory":"512Mi"}}}]'
```

**After mitigation:** Verify next scheduled run completes successfully.

## Verification

- [ ] CronJob shows recent successful LAST SCHEDULE
- [ ] Job pod completed with exit code 0
- [ ] No resource alerts during job execution
- [ ] Expected output/data generated

```bash
kubectl get cronjob <name> -n <namespace>
# Expected: LAST SCHEDULE recent, ACTIVE: 0 (completed)
kubectl get jobs -n <namespace> | grep <cronjob-name> | tail -1
# Expected: COMPLETIONS 1/1
```

## Failure Signals

- Job fails immediately on every attempt (image/config issue)
- Job runs but takes 10x longer than expected (data growth)
- Job causes node resource exhaustion on every run

**If any failure signal is present:** Investigate root cause before re-enabling.

## Rollback

1. **If manual trigger caused issues:** Delete the manual job
2. **If unsuspending caused contention:** Suspend again, fix resources first

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Critical batch job failing repeatedly | Service owner | Direct page | 15 min |
| Batch jobs causing prod degradation | SRE team | #incident-response | 10 min |
| Data pipeline SLA breach due to missed jobs | EM + data team | #data-eng | 30 min |

## Notes

- **startingDeadlineSeconds** must be set. Without it, if the CronJob controller is down during a scheduled time, the job is lost forever.
- **Thundering herd:** Never schedule multiple heavy jobs at the same time. Stagger by 5-10 minutes. See [[INC-040-cronjob-thundering-herd-db]].
- **concurrencyPolicy: Forbid** is safest for most batch jobs — prevents overlap.
- **activeDeadlineSeconds** on the Job spec prevents runaway jobs from running indefinitely.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Suspend a staging CronJob, trigger manually, verify completion.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
