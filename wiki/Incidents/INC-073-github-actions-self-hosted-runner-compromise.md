---
id: INC-073
title: Self-Hosted GitHub Actions Runner Disk Full from Build Artifacts
severity: SEV-3
service: ci-cd
environment: prod
category: capacity
date: 2026-06-21
duration: "1h30m"
tags:
  - incident
  - github-actions
  - ci-cd
  - disk
  - build
  - moderate
  - prod
---

## Summary

All 4 self-hosted GitHub Actions runners filled their 100GB disks with accumulated Docker build cache, test artifacts, and uncleaned workspace directories. New CI jobs entered `queued` state indefinitely, blocking all deployments and pull request checks for 1.5 hours.

## Symptoms

- GitHub Actions: all jobs in `queued` state (no available runners)
- Runner logs: `System.IO.IOException: No space left on device`
- Runner disks: 100% used on all 4 runners
- All PRs stuck waiting for CI checks
- Deployments blocked (CI gate cannot pass)

## Diagnosis

1. Confirmed disk full on runners
   ```bash
   ssh runner-01 df -h /
   # 100G 100G 0 100%
   du -sh /home/runner/actions-runner/_work/* | sort -rh | head -10
   # 35G workspace directories from old runs
   # 40G /var/lib/docker (build cache)
   ```

2. No cleanup job configured — runners accumulate artifacts indefinitely
3. Docker build cache never pruned

## Resolution

1. **Mitigate:** Cleaned up all runners
   ```bash
   for runner in runner-01 runner-02 runner-03 runner-04; do
     ssh $runner "docker system prune -af --volumes && rm -rf /home/runner/actions-runner/_work/*/""
   done
   ```

2. **Fix:** Added daily cleanup cron to each runner
   ```bash
   # Added to crontab: 0 3 * * * docker system prune -af --volumes && find /home/runner/actions-runner/_work -maxdepth 1 -mtime +1 -exec rm -rf {} \;
   ```

3. **Verify:** Runners came back online, queued jobs started executing

## Post-Incident Review

- Self-hosted runners need automated cleanup (unlike GitHub-hosted which are ephemeral)
- Added daily Docker prune and workspace cleanup cron jobs
- Added monitoring: runner disk usage alert at 80%
- Evaluating ephemeral runners (fresh instance per job) to eliminate accumulation

## Links

- Runbooks: [[RB-003-disk-space-full]]
- Related incidents: [[INC-034-github-actions-runner-token-expiry]]
