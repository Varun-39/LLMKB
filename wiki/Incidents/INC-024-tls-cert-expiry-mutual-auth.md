---
id: INC-024
title: Mutual TLS Failure Due to Certificate Expiration
severity: SEV-1
service: api-gateway
environment: prod
category: security
date: 2026-02-03
duration: "52m"
tags:
  - incident
  - tls
  - certificates
  - security
  - mTLS
  - api-gateway
  - critical
---

## Summary

The internal mTLS certificate used by api-gateway to authenticate with downstream microservices expired at 00:00 UTC on 2026-02-03. All service-to-service calls through the gateway returned TLS handshake failures. External API traffic was fully down for 52 minutes affecting all clients.

## Symptoms

- PagerDuty: `API-Gateway-5xx-Critical` at 00:02 UTC
- All downstream services returning HTTP 503 through the gateway
- Gateway logs: `ssl_error:certificate has expired, serial: 3A:F2:...`
- `openssl s_client` showed: `Verify return code: 10 (certificate has expired)`
- cert-manager logs showed no renewal attempt in the last 30 days

## Diagnosis

1. Confirmed certificate expiry:
   ```bash
   kubectl get secret api-gw-mtls-cert -n gateway -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -dates
   # notAfter=Feb  3 00:00:00 2026 GMT
   ```
2. cert-manager Certificate resource showed `Ready=False, Message: certificate has expired`
3. Root cause: cert-manager ACME issuer was configured with DNS-01 challenge, but the DNS provider API token had been rotated 30 days ago without updating the cert-manager secret. Renewal attempts failed silently for 30 days.
4. No alert existed for cert-manager renewal failures

## Resolution

1. Updated the DNS provider API token in cert-manager secret:
   ```bash
   kubectl create secret generic cloudflare-api -n cert-manager --from-literal=api-token=<NEW_TOKEN> --dry-run=client -o yaml | kubectl apply -f -
   ```
2. Triggered manual certificate renewal:
   ```bash
   kubectl delete secret api-gw-mtls-cert -n gateway
   # cert-manager re-issues automatically
   ```
3. Verified new certificate:
   ```bash
   kubectl get certificate api-gw-cert -n gateway
   # READY: True, EXPIRY: 2026-05-04
   ```
4. Restarted gateway pods to pick up new cert:
   ```bash
   kubectl rollout restart deployment api-gateway -n gateway
   ```

## Post-Incident Review

- cert-manager renewal failures were silent — no alerting
- Added Prometheus alert: `certmanager_certificate_ready_status == 0` for > 1 hour
- Added certificate expiry alert: warn at 14 days, critical at 7 days
- Documented API token rotation procedure to include cert-manager secrets

## Links

- Related: [[RB-011-tls-certificate-renewal]]
