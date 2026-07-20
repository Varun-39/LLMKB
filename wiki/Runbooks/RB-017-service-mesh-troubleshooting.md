---
id: RB-017
title: Service Mesh Troubleshooting (Istio/Envoy)
service: "*"
related_services:
  - istio-control-plane
  - api-gateway
  - checkout-service
severity: SEV-2
environment: prod
category: connectivity
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - istio
  - envoy
  - service-mesh
  - networking
  - sidecar
  - prod
related_incidents:
  - "[[INC-041-istio-sidecar-injection-failure]]"
  - "[[INC-051-envoy-circuit-breaker-misconfigured]]"
related_runbooks:
  - "[[RB-007-pod-crash-investigation]]"
  - "[[RB-008-network-saturation-throughput]]"
related_guardrails: []
---

## Purpose

Diagnose and resolve service mesh issues including sidecar injection failures, mTLS errors, circuit breaker misfires, and Envoy configuration problems.

**Desired outcome:** Mesh traffic flowing normally, mTLS working, no connection refused or 503 errors from sidecar.

## Success Criteria

- All pods have istio-proxy sidecar (where expected)
- No `connection refused` or `upstream connect error` in Envoy logs
- mTLS working between services (verified via istioctl)
- Circuit breakers in normal state (not tripped)
- Service-to-service latency at baseline

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any service in the mesh |
| Related services | istio-control-plane, api-gateway, checkout-service |
| Environments | prod, staging |
| Use when | Mesh traffic errors, sidecar injection failures, mTLS errors |
| Do NOT use when | Issue is application-level (not mesh-related) |
| Risk level | Medium |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] `istioctl` CLI access
- [ ] `kubectl` access to affected namespace and istio-system
- [ ] Understanding of which service-to-service call is failing

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `istioctl` | Mesh diagnostics, proxy status | Cluster admin |
| `kubectl` | Pod and config inspection | Cluster admin |
| Kiali | Service mesh visualization | Read access |
| Envoy admin API | Sidecar-level diagnostics | Pod exec |

## Trigger

- Symptom: `connection refused` between services that previously worked
- Symptom: `503 UC (upstream connect error)` in Envoy access logs
- Symptom: New pods missing istio-proxy sidecar container
- Alert: `*-MeshConnectivityError`, `*-mTLSHandshakeFailed`

## Triage

1. Check if sidecar is present
   ```bash
   kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.spec.containers[*].name}'
   # What to look for: istio-proxy should be listed
   ```

2. Check Envoy proxy status
   ```bash
   istioctl proxy-status
   # What to look for: CDS/LDS/EDS/RDS status — SYNCED or NOT SENT
   ```

3. Check for mTLS issues
   ```bash
   istioctl authn tls-check <pod>.<namespace>
   ```

## Investigation

1. **Sidecar injection not working**
   ```bash
   kubectl get namespace <namespace> --show-labels | grep istio-injection
   kubectl get mutatingwebhookconfiguration istio-sidecar-injector -o yaml | grep "service"
   ```

2. **Connection refused between services**
   ```bash
   kubectl exec <pod> -n <namespace> -c istio-proxy -- curl localhost:15000/clusters | grep <target-service>
   # What to look for: health_flags, outlier_detection status
   ```

3. **Circuit breaker tripped**
   ```bash
   kubectl exec <pod> -n <namespace> -c istio-proxy -- curl localhost:15000/stats | grep circuit
   # What to look for: cx_open: 1 = circuit breaker open
   ```

4. **Decision point:**
   - IF sidecar missing → proceed to Mitigation Option A
   - IF mTLS mismatch → proceed to Mitigation Option B
   - IF circuit breaker tripped → proceed to Mitigation Option C
   - IF Envoy config out of sync → proceed to Mitigation Option D

## Mitigation

### Option A: Fix sidecar injection

```bash
# Enable injection on namespace:
kubectl label namespace <namespace> istio-injection=enabled --overwrite
# Fix webhook if pointing to wrong istiod:
kubectl patch mutatingwebhookconfiguration istio-sidecar-injector \
  --type='json' -p='[{"op":"replace","path":"/webhooks/0/clientConfig/service/name","value":"istiod"}]'
# Restart affected pods:
kubectl rollout restart deployment/<deployment> -n <namespace>
```

### Option B: Fix mTLS configuration

```bash
# Check PeerAuthentication:
kubectl get peerauthentication --all-namespaces
# If STRICT mode blocking non-mesh traffic, set PERMISSIVE temporarily:
kubectl apply -f - <<EOF
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: <namespace>
spec:
  mtls:
    mode: PERMISSIVE
EOF
```

### Option C: Reset circuit breaker

```bash
# Remove or adjust DestinationRule outlierDetection:
kubectl patch destinationrule <dr-name> -n <namespace> \
  --type='json' -p='[{"op":"replace","path":"/spec/trafficPolicy/outlierDetection/consecutive5xxErrors","value":10}]'
# Or remove outlierDetection entirely to reset:
kubectl patch destinationrule <dr-name> -n <namespace> \
  --type='json' -p='[{"op":"remove","path":"/spec/trafficPolicy/outlierDetection"}]'
```

### Option D: Force Envoy config resync

```bash
# Restart istiod to force config push:
kubectl rollout restart deployment/istiod -n istio-system
# Or restart specific pod's sidecar:
kubectl delete pod <pod-name> -n <namespace>
```

**After mitigation:** Verify mesh traffic flowing via istioctl or Kiali.

## Verification

- [ ] All pods have istio-proxy sidecar
- [ ] `istioctl proxy-status` shows all SYNCED
- [ ] No connection errors in Envoy access logs
- [ ] mTLS verified via `istioctl authn tls-check`

```bash
istioctl proxy-status | grep -v "SYNCED.*SYNCED.*SYNCED.*SYNCED"
# Expected: empty (all synced)
```

## Failure Signals

- Pods still missing sidecar after namespace label fix
- mTLS errors persist after policy change
- Circuit breaker continues tripping (underlying service issue)
- istiod not pushing config to proxies

**If any failure signal is present:** Escalate.

## Rollback

1. **Undo PeerAuthentication change:** Revert to STRICT
2. **Undo DestinationRule change:** Restore from git
3. **If mesh itself is broken:** Disable injection, restart pods without sidecars (bypasses mesh)

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Mesh-wide connectivity failure | Platform team | PagerDuty P1 | Immediate |
| istiod not responding | Platform team | #platform-support | 10 min |
| mTLS breaking cross-namespace calls | Security + Platform | #incident-response | 10 min |

## Notes

- **Sidecar injection only happens at pod creation time.** Existing pods must be restarted to get/remove sidecars.
- **istiod version must match sidecar proxy version** within one minor version.
- **Circuit breakers protect the mesh but can cause cascading failures** if thresholds are too aggressive. See [[INC-051-envoy-circuit-breaker-misconfigured]].

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Deploy test pod in mesh-enabled namespace, verify sidecar injection and mTLS.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Platform Team | Initial publication |
