---
id: INC-034
title: GitHub Actions Self-Hosted Runner Token Expiry
severity: SEV-3
service: ci-cd
environment: prod
category: configuration
date: 2026-04-05
duration: "4h"
tags:
  - incident
  - github-actions
  - ci-cd
  - token
  - runner
  - authentication
---

## Summary

All self-hosted GitHub Actions runners went offline after their registration tokens expired. The tokens (valid for 24 hours) were hardcoded in the runner deployment and not automatically refreshed. All CI/CD pipelines were blocked for 4 hours until discovered during business hours.

## Symptoms

- GitHub UI: all self-hosted runners showing `Offline` since 02:00 UTC
- CI workflows queued indefinitely: `Waiting for a runner to pick up this job`
- Runner logs: `Http response code: Unauthorized from 'POST https://api.github.com/actions/runners/registration-token'`
- 47 PRs blocked from merging (no CI status)

## Diagnosis

1. Runner pod logs:
   ```
   Removing runner... (token invalid)
   Failed to connect: The running operation has been cancelled.
   ```
2. Registration token was generated once during initial deployment (March 1)
3. GitHub runner tokens expire after 1 hour for registration — the runner was using a stale token stored in a Kubernetes secret
4. No token rotation mechanism existed

## Resolution

1. Generated fresh registration token via API:
   ```bash
   curl -X POST -H "Authorization: token $GH_PAT" \
     https://api.github.com/repos/org/repo/actions/runners/registration-token
   ```
2. Updated Kubernetes secret with new token:
   ```bash
   kubectl create secret generic gh-runner-token --from-literal=token=<NEW_TOKEN> -n ci --dry-run=client -o yaml | kubectl apply -f -
   ```
3. Restarted runner pods
4. Confirmed runners registered and picked up queued jobs

## Post-Incident Review

- Runner tokens must be refreshed programmatically — not stored as static secrets
- Implemented a CronJob that refreshes the registration token every 30 minutes
- Added monitoring: alert if no runner heartbeat for > 10 minutes
- Migrated to GitHub's recommended `actions-runner-controller` which handles token lifecycle automatically

## Links

- Related: [[RB-025-container-registry-auth-failure]]
