---
id: INC-063
title: Node Clock Skew Caused TLS Certificate Validation Failures
severity: SEV-2
service: api-gateway
environment: prod
category: outage
date: 2026-06-05
duration: "18m"
tags:
  - incident
  - ntp
  - clock-skew
  - tls
  - certificates
  - kubernetes
  - high
  - prod
error_family: tls-cert-expiry
resolution_runbook: RB-009
resolution_outcome: resolved
---

## Summary

At 06:30 UTC on 2026-06-05, worker-node-07's system clock drifted 15 minutes into the future after the NTP daemon (chronyd) crashed silently 3 days earlier. All TLS handshakes from pods on this node failed with `certificate is not yet valid` because the node's time was ahead of certificate `notBefore` times. Services on this node returned 502 errors on all outbound HTTPS calls.

## Symptoms

- api-gateway pods on node-07: `x509: certificate has expired or is not yet valid`
- Outbound HTTPS calls from node-07: 100% failure
- Other nodes: unaffected
- chronyd on node-07: `inactive (dead)` since 3 days ago

## Diagnosis

1. Confirmed clock skew
   ```bash
   ssh ec2-user@worker-node-07 date
   # Shows time 15 minutes ahead of actual UTC
   timedatectl status
   # NTP synchronized: no
   ```

2. chronyd had crashed due to corrupted drift file
   ```bash
   systemctl status chronyd
   # Active: inactive (dead) since Jun-02
   journalctl -u chronyd | tail -5
   # Fatal error: could not parse drift file
   ```

3. Only pods on node-07 affected (all TLS validation uses system clock)

## Resolution

1. **Mitigate:** Cordoned node and restarted chronyd
   ```bash
   kubectl cordon worker-node-07
   ssh ec2-user@worker-node-07
   rm /var/lib/chrony/drift
   systemctl restart chronyd
   chronyc makestep 1 -1
   ```

2. **Fix:** Clock synced, pods rescheduled
   ```bash
   kubectl drain worker-node-07 --ignore-daemonsets --delete-emptydir-data
   kubectl uncordon worker-node-07
   ```

3. **Verify:** TLS connections working from all nodes

## Post-Incident Review

- NTP daemon failure went undetected for 3 days
- Added monitoring: alert if `chrony_tracking_offset_seconds > 1` for >5 minutes
- Added node health check: clock skew >5s = node marked unhealthy
- chronyd configured with auto-restart on failure via systemd

## Links

- Runbooks: [[RB-009-etcd-cluster-recovery]]
- Related incidents: [[INC-022-mtls-certificate-expiration]]
