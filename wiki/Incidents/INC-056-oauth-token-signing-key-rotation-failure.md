---
id: INC-056
title: OAuth Token Signing Key Rotation — All Tokens Invalidated
severity: SEV-1
service: auth-service
environment: prod
category: outage
date: 2026-05-18
duration: "38m"
tags:
  - incident
  - oauth
  - jwt
  - signing-key
  - auth
  - critical
  - prod
---

## Summary

At 14:00 UTC on 2026-05-18, an automated key rotation job replaced the JWT signing key without maintaining the previous key for verification. All existing access tokens in circulation became invalid instantly, logging out 100% of active users. The auth-service correctly issued new tokens on re-login, but the sudden invalidation created a login storm that overwhelmed the auth database for 38 minutes.

## Symptoms

- PagerDuty: `AuthService-401ErrorRateHigh` at 14:02 UTC
- All API endpoints: 401 Unauthorized for all requests with existing tokens
- auth-service: `InvalidSignatureException: JWT signature does not match`
- Login endpoint: 12x normal traffic (all users forced to re-authenticate)
- auth-db: connection pool exhausted from login storm

## Impact

| Dimension | Detail |
|-----------|--------|
| Users affected | 100% of active users (~28,000) logged out |
| Services degraded | auth-service (overwhelmed), all API endpoints (401) |
| Revenue impact | ~$45K in lost transactions during storm |
| Duration | 14:00 → 14:38 UTC (38 min) |
| Data loss | None |
| SLA breach | Yes — auth SLA (99.95%) breached |
| Customer comms | Status page updated at 14:05, email at 14:15 |

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 14:00 | Key rotation CronJob ran, replaced signing key |
| 14:01 | First 401 errors on all endpoints |
| 14:02 | Alert fired: `AuthService-401ErrorRateHigh` |
| 14:03 | On-call acknowledged (Priya Sharma) |
| 14:10 | Key rotation identified as cause |
| 14:15 | Previous signing key restored to JWKS endpoint for verification |
| 14:18 | Existing tokens valid again, login storm subsided |
| 14:25 | auth-db connection pool recovered |
| 14:38 | All services at baseline, incident closed |

## Diagnosis

1. Confirmed mass 401 errors
   ```bash
   kubectl logs -l app=api-gateway -n api --tail=100 | grep -c "401"
   # 8,400 in last 60 seconds (normal: ~5)
   ```

2. Checked JWKS endpoint
   ```bash
   curl https://auth.internal/.well-known/jwks.json | jq '.keys | length'
   # 1 (should be 2 — current + previous for rotation)
   ```

3. Key rotation job had removed old key immediately instead of keeping it for token lifetime

## Resolution

1. **Mitigate:** Re-added previous signing key to JWKS endpoint
   ```bash
   kubectl patch secret auth-signing-keys -n auth --type='json' \
     -p='[{"op":"add","path":"/data/previous-key","value":"<base64-previous-key>"}]'
   kubectl rollout restart deployment/auth-service -n auth
   ```

2. **Fix:** Rewrote key rotation to maintain previous key for token TTL + 1 hour

3. **Verify:** Existing tokens accepted, no more 401 storm

## Post-Incident Review

- Key rotation must be additive (add new, keep old for token lifetime)
- Rewrote rotation CronJob to maintain N-1 and N keys in JWKS
- Added integration test: rotate key, verify existing tokens still validate
- Added alert: if JWKS has fewer than 2 keys, page immediately

## Links

- Runbooks: [[RB-012-vault-sealed-recovery]]
- Related incidents: [[INC-019-broken-feature-flag-auth]]
