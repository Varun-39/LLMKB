---
id: INC-096
title: mTLS Handshake Timeout Spike After Istio Sidecar Version Mismatch
severity: SEV-2
service: api-gateway
environment: prod
category: degradation
date: 2026-05-03
duration: "40m"
tags:
  - incident
  - istio
  - mtls
  - tls
  - sidecar
  - version-mismatch
  - api-gateway
  - prod
---

## Summary

A rolling upgrade of the Istio control plane to 1.21 was performed while data-plane sidecars remained on 1.19. The 1.19 sidecar on api-gateway pods failed to complete mTLS handshakes with 1.21 sidecars on downstream services, causing connection errors that presented as 503s. The mismatch went undetected because the upgrade procedure skipped the mandatory sidecar restart step.

## Symptoms

- api-gateway logs: `upstream connect error or disconnect/reset before headers. reset reason: connection failure`
- Istio proxy logs: `TLS handshake timeout` between api-gateway (1.19) and payment-service (1.21)
- HTTP 503 error rate on api-gateway: 18%
- `istioctl proxy-status`: api-gateway shows `STALE` sync state

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~9,000 API calls failed |
| Services degraded | api-gateway → payment-service, auth-service connections |
| Revenue impact | ~$8.4K |
| Duration | 14:30 → 15:10 UTC (40 min) |
| Data loss | None |
| SLA breach | Yes — API error rate SLA breached |
| Customer comms | Status page updated at 14:35 UTC |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 14:00 | Istio control plane upgraded to 1.21 |
| 14:15 | Downstream service sidecars restarted (1.21) |
| 14:30 | api-gateway sidecar skipped restart — remains on 1.19 |
| 14:30 | mTLS handshake failures begin |
| 14:35 | Error rate alert fires |
| 14:45 | On-call identifies sidecar version mismatch |
| 15:10 | api-gateway pods restarted; sidecars upgraded to 1.21 |

## Diagnosis

1. Checked proxy versions:
   ```bash
   istioctl proxy-status
   # api-gateway-pod-xxx: VERSION=1.19.x  SYNC=STALE
   # payment-service-pod-xxx: VERSION=1.21.x SYNC=SYNCED
   ```
2. Confirmed handshake errors in proxy logs:
   ```bash
   kubectl logs -n api api-gateway-pod-xxx -c istio-proxy | grep "TLS handshake"
   # [warning] TLS handshake timeout, peer=payment-service
   ```
3. Verified TLS policy requires strict mTLS:
   ```bash
   kubectl get peerauthentication -n payments
   # payment-mtls-strict: mode=STRICT
   ```

## Resolution

1. **Restarted api-gateway pods** to pick up new sidecar (1.21):
   ```bash
   kubectl rollout restart deployment/api-gateway -n api
   ```
2. **Verified version consistency:**
   ```bash
   istioctl proxy-status | grep api-gateway
   # VERSION=1.21.x SYNC=SYNCED
   ```
3. Error rate dropped to baseline within 3 minutes of restart

## Post-Incident Review

**What went well:**
- Version mismatch is visible via `istioctl proxy-status` — diagnosis was fast

**What needs improvement:**
- Upgrade procedure did not include mandatory sidecar restart for all affected namespaces
- No automated check for sidecar version drift post-upgrade

**Action items:**

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add post-upgrade step: restart all deployments after control plane upgrade | Platform | 2026-05-10 | Open |
| Add alert: `istio_proxy_version` differs from control plane version | Observability | 2026-05-10 | Open |

## Links

- Runbooks: [[RB-017-service-mesh-troubleshooting]]
- Related incidents: [[INC-041-istio-sidecar-injection-failure]], [[INC-024-tls-cert-expiry-mutual-auth]]
