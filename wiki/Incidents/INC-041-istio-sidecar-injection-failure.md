---
id: INC-041
title: Istio Sidecar Injection Failure After Control Plane Upgrade
severity: SEV-2
service: api-gateway
environment: prod
category: deployment-failure
date: 2026-03-25
duration: "32m"
detection_gap: "8m"
tags:
  - incident
  - istio
  - service-mesh
  - sidecar
  - kubernetes
  - high
  - prod
---

## Summary

After upgrading Istio control plane from 1.19 to 1.20 at 09:00 UTC on 2026-03-25, newly created pods in the `api` namespace failed to receive sidecar injection. The mutating webhook was misconfigured during the upgrade, pointing to the old `istiod-1-19` service that no longer existed. Pods started without sidecars had no mTLS, breaking service-to-service communication for 32 minutes until the webhook was corrected.

## Symptoms

- No immediate alert (detection gap: 8 min)
- First symptom: api-gateway pods failing health checks after routine restart at 09:08
- Pod logs: `connection refused` on all mesh-internal calls
- `istio-proxy` container missing from newly created pods
- Existing pods (with sidecars) unaffected

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | ~4,000 users on requests hitting new pods |
| Services degraded | api-gateway (new pods), any pod restarted post-upgrade |
| Revenue impact | ~$8K in failed API calls |
| Duration | 09:08 → 09:40 UTC (32 min) |
| Data loss | None |
| SLA breach | No — partial degradation |
| Customer comms | N/A |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 09:00 | Istio control plane upgrade 1.19 → 1.20 completed |
| 09:08 | api-gateway pod recycled, new pod has no sidecar |
| 09:16 | Alert fired: `APIGateway-HealthCheckFailing` |
| 09:18 | On-call acknowledged (Maria Santos) |
| 09:28 | Webhook misconfiguration identified |
| 09:32 | Webhook patched to point to `istiod` (1.20) |
| 09:35 | api-gateway pods restarted with sidecars |
| 09:40 | All services healthy, incident closed |

## Diagnosis

1. Checked pod containers
   ```bash
   kubectl get pod api-gateway-new-xyz -n api -o jsonpath='{.spec.containers[*].name}'
   # api-gateway (missing istio-proxy)
   ```

2. Checked mutating webhook configuration
   ```bash
   kubectl get mutatingwebhookconfigurations istio-sidecar-injector -o yaml | grep service
   # service: istiod-1-19 (does not exist)
   ```

3. Confirmed istiod-1-19 was removed during upgrade
   ```bash
   kubectl get svc -n istio-system | grep istiod
   # istiod (1.20 only)
   ```

## Resolution

1. **Mitigate:** Patched webhook to reference correct service
   ```bash
   kubectl patch mutatingwebhookconfiguration istio-sidecar-injector \
     --type='json' -p='[{"op":"replace","path":"/webhooks/0/clientConfig/service/name","value":"istiod"}]'
   ```

2. **Fix:** Restarted affected deployments
   ```bash
   kubectl rollout restart deployment/api-gateway -n api
   ```

3. **Verify:** New pods have sidecar, mesh communication restored

## Post-Incident Review

- Istio upgrade procedure did not include webhook validation step
- Added post-upgrade check: verify webhook points to active istiod service
- Added canary namespace test: create a test pod and verify sidecar injection before upgrading remaining namespaces

## Links

- Runbooks: [[RB-017-service-mesh-troubleshooting]]
- Related incidents: [[INC-028-k8s-admission-webhook-timeout]]
