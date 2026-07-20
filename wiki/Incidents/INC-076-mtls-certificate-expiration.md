---
id: INC-076
title: Mutual TLS Certificate Expiration Causing Service Mesh Failure
severity: SEV-1
service: service-mesh
environment: prod
category: security
date: 2026-01-15
duration: "62m"
tags:
  - incident
  - tls
  - certificates
  - service-mesh
  - security
---

## Summary

Mutual TLS certificates used by the Istio service mesh expired at 02:00 UTC, causing all inter-service communication to fail with TLS handshake errors. Approximately 40 microservices lost connectivity for 62 minutes until emergency certificate rotation was completed.

## Symptoms

- Spike in `upstream_cx_ssl_handshake_error` across all Envoy sidecars
- All inter-service HTTP calls returning 503 with `UNAVAILABLE:TLS handshake failed`
- PagerDuty alert: `ServiceMesh-mTLS-HandshakeFailures-Critical`
- Grafana dashboard showing 0% success rate on all service-to-service calls
- Application logs: `error: x509: certificate has expired or is not yet valid`

## Diagnosis

1. Checked Envoy sidecar logs: `SSL error: certificate verify failed (certificate has expired)`
2. Inspected cert expiry: `istioctl proxy-config secret <pod> | grep EXPIRY` showed certs expired at 02:00 UTC
3. Confirmed Istio citadel had failed to rotate certs due to a stuck leader election after a node restart 72 hours prior
4. Root cause: Citadel pod was restarted during maintenance but lost its leader lease; the new leader never triggered cert renewal

## Resolution

1. Force-rotated all mesh certificates: `istioctl experimental create-remote-secret` and restarted citadel
2. Verified new certs issued: `istioctl proxy-config secret <pod>` showed valid expiry
3. Rolling restart of all sidecars: `kubectl rollout restart deployment -n <ns>` across all namespaces
4. Confirmed service-to-service traffic restored via Grafana dashboards

## Post-Incident Review

Added certificate expiry monitoring with 7-day advance alerting. Implemented citadel leader election health check. Added runbook for emergency cert rotation. Reduced cert TTL from 90 days to 30 days to catch rotation failures earlier.

## Links
- Related: [[RB-011-tls-certificate-renewal]]
