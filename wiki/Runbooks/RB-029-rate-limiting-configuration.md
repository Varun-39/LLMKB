---
id: RB-029
title: Rate Limiting Configuration and Abuse Mitigation
service: api-gateway
related_services:
  - ingress-controller
  - search-api
  - auth-service
severity: SEV-2
environment: prod
category: performance
risk_level: medium
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - rate-limit
  - api
  - abuse
  - traffic
  - prod
related_incidents:
  - "[[INC-068-api-rate-limit-bypass-header-spoofing]]"
  - "[[INC-020-bad-config-rollout-payment]]"
related_runbooks:
  - "[[RB-020-haproxy-connection-saturation-recovery]]"
  - "[[RB-004-high-cpu-usage]]"
related_guardrails: []
---

## Purpose

Configure, debug, or emergency-apply rate limits to protect services from traffic spikes, abuse, or misconfigured clients.

**Desired outcome:** Abusive traffic blocked, legitimate traffic flowing, backend services protected from overload.

## Success Criteria

- Abusive traffic returning 429 (rate limited)
- Legitimate traffic flowing with <0.1% false positive rate
- Backend service CPU and latency at baseline
- Rate limit rules active and logging

## Scope

| Attribute | Value |
|-----------|-------|
| Service | api-gateway |
| Related services | ingress-controller, search-api, auth-service |
| Environments | prod |
| Use when | Traffic spike overwhelming backend, suspected abuse, DDoS-like patterns |
| Do NOT use when | Backend is genuinely slow (fix the backend) |
| Risk level | Medium (wrong rate limit can block legitimate users) |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] Access to rate limit configuration (ConfigMap, ingress annotations, WAF)
- [ ] Knowledge of normal traffic patterns for the endpoint
- [ ] Ability to identify abusive traffic source

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | ConfigMap and ingress operations | Cluster admin |
| WAF Console | Rule management | Write access |
| Access logs | Traffic analysis | Read access |
| Grafana | Traffic rate dashboards | Read access |

## Trigger

- Backend service overwhelmed by traffic (CPU >90%, latency spike)
- Suspected DDoS or scraping activity
- Single client/IP consuming disproportionate resources
- Alert: `*-TrafficSpikeDetected`, `*-AbuseDetected`

## Triage

1. Identify the traffic pattern
   ```bash
   kubectl logs -l app=ingress-nginx -n ingress-system --tail=1000 | \
     awk '{print $1}' | sort | uniq -c | sort -rn | head -10
   # What to look for: single IP or small set of IPs with disproportionate requests
   ```

2. Identify the targeted endpoint
   ```bash
   kubectl logs -l app=ingress-nginx -n ingress-system --tail=1000 | \
     awk '{print $7}' | sort | uniq -c | sort -rn | head -10
   # What to look for: single endpoint getting hammered
   ```

3. Determine if traffic is legitimate or abusive

## Mitigation

### Option A: Emergency per-IP rate limit at ingress

```bash
kubectl annotate ingress <name> -n <namespace> \
  nginx.ingress.kubernetes.io/limit-rps="10" \
  nginx.ingress.kubernetes.io/limit-connections="5"
```

### Option B: Block specific IP/CIDR

```bash
kubectl annotate ingress <name> -n <namespace> \
  nginx.ingress.kubernetes.io/configuration-snippet='deny 203.0.113.0/24;'
# Or via WAF:
aws wafv2 update-ip-set --name blocked-ips --id <id> --addresses "203.0.113.0/24"
```

### Option C: Rate limit specific endpoint

```bash
# Add rate limit ConfigMap for specific path:
kubectl patch configmap nginx-configuration -n ingress-system --type merge \
  -p '{"data":{"limit-req-status-code":"429"}}'
```

### Option D: Enable WAF rate-based rule

```bash
aws wafv2 update-web-acl --name prod-acl --id <id> \
  --rules '[{"Name":"rate-limit","Priority":1,"Statement":{"RateBasedStatement":{"Limit":2000,"AggregateKeyType":"IP"}},"Action":{"Block":{}},"VisibilityConfig":{...}}]'
```

**After mitigation:** Monitor — abusive traffic getting 429, legitimate traffic unaffected.

## Verification

- [ ] Abusive source receiving 429 responses
- [ ] Legitimate traffic flowing normally (spot check)
- [ ] Backend service CPU/latency recovered
- [ ] Rate limit rules active in configuration

```bash
curl -s -o /dev/null -w "%{http_code}" -H "X-Real-IP: <abusive-ip>" https://<domain>/api/search
# Expected: 429
curl -s -o /dev/null -w "%{http_code}" https://<domain>/api/search
# Expected: 200 (legitimate)
```

## Failure Signals

- Legitimate users getting 429 (false positives)
- Attacker rotating IPs (bypassing IP-based limits)
- Rate limit not taking effect (config not reloaded)

## Rollback

1. **Remove rate limit annotations:**
   ```bash
   kubectl annotate ingress <name> -n <namespace> nginx.ingress.kubernetes.io/limit-rps- nginx.ingress.kubernetes.io/limit-connections-
   ```
2. **Remove IP block:** Remove deny snippet from annotation
3. **Disable WAF rule:** Set action to Count instead of Block

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Large-scale DDoS (WAF insufficient) | Security + AWS Shield | #security-urgent | Immediate |
| Cannot identify abusive source | Security team | #security | 15 min |
| Legitimate users being rate limited | Product team + SRE | #incident-response | 10 min |

## Notes

- **Never trust X-Forwarded-For for rate limiting.** Use the real connection IP from the last trusted proxy. See [[INC-068-api-rate-limit-bypass-header-spoofing]].
- **Rate limit = 0 means unlimited** in some configurations. Always verify the rule is actually limiting. See [[INC-020-bad-config-rollout-payment]].
- **Start with logging (monitor mode) before blocking** to gauge false positive rate.
- **Per-endpoint rate limits** are more effective than global — search endpoints typically need stricter limits.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Monthly
- **Next review:** 2026-07-15
- **Test method:** Generate test traffic above threshold, verify 429 responses.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | Security + SRE Team | Initial publication |
