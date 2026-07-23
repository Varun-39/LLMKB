---
id: INC-046
title: cert-manager Hit Let's Encrypt Rate Limit — TLS Renewals Blocked
severity: SEV-2
service: cert-manager
environment: prod
category: configuration
date: 2026-04-20
duration: "4h"
tags:
  - incident
  - tls
  - certificates
  - letsencrypt
  - rate-limit
  - high
  - prod
error_family: tls-cert-expiry
resolution_runbook: RB-011
resolution_outcome: resolved
---

## Summary

On 2026-04-20, cert-manager exhausted the Let's Encrypt rate limit (50 certificates per registered domain per week) after a misconfigured ClusterIssuer repeatedly requested new certificates for wildcard subdomains instead of renewing existing ones. Existing certificates continued working, but 8 services with certificates expiring within the next 24 hours could not renew, creating a ticking clock until TLS failures would begin.

## Symptoms

- cert-manager logs: `429 Too Many Requests: Rate limit reached for new orders`
- 8 certificates with `Renewing` status stuck for 2+ hours
- No immediate user impact (existing certs still valid)
- cert-manager events: `Failed to create Order: 429`

## Diagnosis

1. Confirmed rate limit hit
   ```bash
   kubectl logs -l app=cert-manager -n cert-manager --tail=100 | grep "429"
   # 429 Too Many Requests — 47 times in last hour
   ```

2. Found misconfigured issuer creating new certs instead of renewing
   ```bash
   kubectl get certificates --all-namespaces | grep -c "True"
   # 62 certificates issued this week (limit: 50)
   ```

3. A deployment script was recreating Certificate resources on each deploy instead of leaving them in place

## Resolution

1. **Mitigate:** Switched expiring certificates to a pre-provisioned wildcard cert from AWS ACM as temporary fallback

2. **Fix:** Fixed deployment script to not recreate Certificate CRDs; waited for rate limit window to expire (168 hours)

3. **Verify:** All certificates renewed after rate limit window reset

## Post-Incident Review

- Deployment script used `kubectl apply --force` which recreated Certificate resources
- Changed to standard `kubectl apply` which updates in place
- Added monitoring: alert if >30 certificate requests in a 24-hour window
- Configured cert-manager to use DNS-01 challenge with staging issuer for testing

## Links

- Runbooks: [[RB-011-tls-certificate-renewal]]
- Related incidents: [[INC-024-tls-cert-expiry-mutual-auth]]
