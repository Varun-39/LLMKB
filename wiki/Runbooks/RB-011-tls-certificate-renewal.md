---
id: RB-011
title: TLS Certificate Renewal and Expiry Recovery
service: "*"
related_services:
  - ingress-controller
  - cert-manager
  - api-gateway
severity: SEV-1
environment: prod
category: connectivity
risk_level: high
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - tls
  - certificates
  - renewal
  - ingress
  - prod
related_incidents:
  - "[[INC-022-mtls-certificate-expiration]]"
  - "[[INC-024-tls-cert-expiry-mutual-auth]]"
  - "[[INC-046-cert-manager-acme-rate-limit]]"
related_runbooks:
  - "[[RB-006-failed-deployment-rollback]]"
related_guardrails: []
---

## Purpose

Diagnose and resolve TLS certificate expiry or renewal failures, covering cert-manager issues, manual certificate rotation, and emergency fallback procedures.

**Desired outcome:** Valid TLS certificates serving on all endpoints, no browser warnings, no connection failures.

## Success Criteria

- `openssl s_client` shows valid certificate with >7 days remaining
- No TLS handshake errors in logs
- cert-manager Certificate resources in `Ready: True` state
- All HTTPS endpoints returning 200 without certificate errors

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any service with TLS termination |
| Related services | ingress-controller, cert-manager, api-gateway |
| Environments | prod, staging |
| Use when | `*-CertExpiring`, `*-TLSHandshakeError`, certificate expired alerts |
| Do NOT use when | TLS error is caused by client-side CA trust issues |
| Risk level | High (expired cert = full outage for HTTPS) |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to cert-manager namespace and affected namespace
- [ ] `openssl` CLI available
- [ ] Access to cert-manager logs
- [ ] DNS access for domain verification (if ACME renewal needed)

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | cert-manager and ingress operations | Cluster admin |
| `openssl` | Certificate inspection | Local tool |
| cert-manager CLI (`cmctl`) | Certificate status and renewal trigger | Cluster admin |
| AWS ACM Console | Fallback certificate management | Write access |

## Trigger

- Alert: `*-CertExpiring` (certificate expires in <7 days)
- Alert: `*-TLSHandshakeError`
- Symptom: Browser showing "NET::ERR_CERT_DATE_INVALID"
- Symptom: cert-manager Certificate resource status `Ready: False`
- Metric: SSL handshake error rate spike

## Triage

1. Check certificate expiry from outside
   ```bash
   echo | openssl s_client -servername <domain> -connect <domain>:443 2>/dev/null | openssl x509 -noout -dates
   # What to look for: notAfter date — is it past or within 24h?
   ```

2. Check cert-manager Certificate status
   ```bash
   kubectl get certificates --all-namespaces
   kubectl describe certificate <cert-name> -n <namespace>
   # What to look for: Ready=False, conditions showing failure reason
   ```

3. Wrong symptoms? Not cert-related? → Check DNS or network connectivity.

## Investigation

1. **Check cert-manager logs for renewal failure reason**
   ```bash
   kubectl logs -l app=cert-manager -n cert-manager --tail=100 | grep -i "error\|failed\|challenge"
   ```

2. **Check ACME challenge status**
   ```bash
   kubectl get challenges --all-namespaces
   kubectl describe challenge <challenge-name> -n <namespace>
   # What to look for: DNS propagation failure, HTTP validation failure, rate limit
   ```

3. **Check if Let's Encrypt rate limit hit**
   ```bash
   kubectl logs -l app=cert-manager -n cert-manager --tail=50 | grep "429\|rate limit"
   ```

4. **Decision point:**
   - IF cert-manager renewal failing (ACME challenge) → proceed to Mitigation Option A
   - IF rate limit hit → proceed to Mitigation Option B
   - IF certificate already expired → proceed to Mitigation Option C
   - IF cert-manager itself is down → proceed to Mitigation Option D

## Mitigation

### Option A: Force cert-manager renewal

```bash
cmctl renew <certificate-name> -n <namespace>
# Or delete the secret to trigger re-issuance:
kubectl delete secret <cert-secret-name> -n <namespace>
# cert-manager will detect missing secret and re-issue
```

### Option B: Rate limit — use alternative issuer

```bash
# Switch to a different ACME CA or use AWS ACM as temporary fallback
kubectl patch certificate <cert-name> -n <namespace> \
  --type='json' -p='[{"op":"replace","path":"/spec/issuerRef/name","value":"letsencrypt-staging"}]'
# Or import a pre-provisioned wildcard cert
kubectl create secret tls emergency-cert -n <namespace> \
  --cert=fullchain.pem --key=privkey.pem
kubectl patch ingress <ingress-name> -n <namespace> \
  --type='json' -p='[{"op":"replace","path":"/spec/tls/0/secretName","value":"emergency-cert"}]'
```

### Option C: Certificate already expired — emergency replacement

```bash
# Import backup wildcard certificate:
kubectl create secret tls emergency-wildcard -n <namespace> \
  --cert=/backup/wildcard.pem --key=/backup/wildcard-key.pem
# Update ingress to use it:
kubectl patch ingress <ingress-name> -n <namespace> \
  --type='json' -p='[{"op":"replace","path":"/spec/tls/0/secretName","value":"emergency-wildcard"}]'
# Restart ingress controller to pick up:
kubectl rollout restart deployment/nginx-ingress -n ingress-system
```

### Option D: cert-manager down — restart

```bash
kubectl rollout restart deployment/cert-manager -n cert-manager
kubectl rollout status deployment/cert-manager -n cert-manager --timeout=120s
```

**After mitigation:** Verify TLS serving correctly with `openssl s_client`.

## Verification

- [ ] `openssl s_client` shows valid cert with >7 days remaining
- [ ] No TLS errors in ingress logs
- [ ] Certificate resource shows `Ready: True`
- [ ] HTTPS endpoint returns 200

```bash
echo | openssl s_client -servername <domain> -connect <domain>:443 2>/dev/null | openssl x509 -noout -dates -subject
# Expected: notAfter in the future, correct CN/SAN
curl -s -o /dev/null -w "%{http_code}" https://<domain>/health
# Expected: 200
```

## Failure Signals

- cert-manager unable to solve ACME challenge (DNS not propagating)
- Rate limit not expiring (weekly window)
- Emergency cert also expired or wrong domain
- Ingress controller not picking up new secret

**If any failure signal is present:** Proceed to Escalation.

## Rollback

1. **If wrong cert deployed:** Restore original secret from backup
2. **If ingress broken:** Revert ingress annotation changes
3. **If cert-manager misconfigured:** Restore ClusterIssuer from git

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Cannot renew within 15 min | Platform team | #platform-support | 10 min |
| Certificate expired and no backup available | EM + Platform Lead | PagerDuty P1 | Immediate |
| DNS challenge failing (DNS provider issue) | DNS/infra team | #platform-support | 10 min |
| Rate limit hit, no alternative CA | Security team | #security | 15 min |

## Notes

- **Certificates should auto-renew 30 days before expiry.** If you're seeing expiry alerts, auto-renewal has been broken for weeks.
- **Let's Encrypt rate limits:** 50 certs per registered domain per week. See [[INC-046-cert-manager-acme-rate-limit]].
- **Keep emergency wildcard certificates** updated quarterly in a break-glass secret store.
- **cert-manager CRD version mismatch** after upgrade can silently break renewal. Check CRD versions match controller version.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Monthly (certificates are time-critical)
- **Next review:** 2026-07-15
- **Test method:** Let staging cert expire intentionally, execute emergency rotation.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
