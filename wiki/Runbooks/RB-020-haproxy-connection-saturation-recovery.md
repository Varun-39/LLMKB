---
id: RB-020
title: HAProxy/Load Balancer Connection Saturation Recovery
service: load-balancer
related_services:
  - api-gateway
  - search-api
  - all-backend-services
severity: SEV-1
environment: prod
category: capacity
risk_level: high
estimated_duration: "15m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - haproxy
  - load-balancer
  - connections
  - capacity
  - networking
  - prod
related_incidents:
  - "[[INC-033-haproxy-connection-pool-exhaustion]]"
related_runbooks:
  - "[[RB-008-network-saturation-throughput]]"
related_guardrails: []
---

## Purpose

Diagnose and recover from HAProxy or load balancer connection pool exhaustion, covering slow backends, connection limits, and traffic management.

**Desired outcome:** Connection count below 70% of maxconn, all backends responding within timeout, no queued connections.

## Success Criteria

- HAProxy `scur` (sessions current) below 70% of `slim` (session limit)
- Backend queue depth: 0
- No 503 or connection timeout errors
- All backend health checks passing
- API latency at pre-incident baseline

## Scope

| Attribute | Value |
|-----------|-------|
| Service | load-balancer (HAProxy) |
| Related services | api-gateway, search-api, all backend services |
| Environments | prod |
| Use when | `HAProxy-MaxconnReached`, `Backend-QueueDepthHigh` alerts |
| Do NOT use when | Backend is intentionally drained for maintenance |
| Risk level | High (mishandled → full outage) |
| Estimated duration | 10–15 minutes |
| Approval required | No |

## Prerequisites

- [ ] HAProxy stats socket access
- [ ] `socat` installed on HAProxy host
- [ ] Knowledge of HAProxy backend configuration
- [ ] Access to backend service diagnostics

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `socat` + HAProxy stats socket | Runtime stats and admin commands | Admin |
| `kubectl` | Backend service operations | Cluster admin |
| Grafana | Connection metrics dashboard | Read access |
| HAProxy config | Configuration review | Read access |

## Trigger

- Alert: `HAProxy-MaxconnReached` (scur >= slim)
- Alert: `HAProxy-BackendQueueDepthHigh`
- Symptom: HTTP 503 on all endpoints, `no server available`
- Symptom: Client-side connection timeouts
- Metric: HAProxy sessions current approaching maxconn limit

## Triage

1. Check current connection state
   ```bash
   echo "show stat" | socat stdio /var/run/haproxy.sock | cut -d, -f1,2,5,8,18,34
   # What to look for: scur (current sessions), slim (session limit), qcur (queue current)
   ```

2. Identify slow backend(s)
   ```bash
   echo "show stat" | socat stdio /var/run/haproxy.sock | awk -F, '$18>5000{print $1,$2,$18}'
   # What to look for: backend response time (rtime) >5000ms = slow backend holding connections
   ```

3. Check if it's connection limit or slow backend
   ```bash
   echo "show info" | socat stdio /var/run/haproxy.sock | grep -i "curr.*conn\|max.*conn"
   ```

## Investigation

1. **Which backend is causing the pile-up?**
   ```bash
   echo "show stat" | socat stdio /var/run/haproxy.sock | grep -i "BACKEND" | awk -F, '{print $1,$5,$8,$18}'
   # What to look for: high qcur + high rtime = that backend is the culprit
   ```

2. **Check backend health**
   ```bash
   echo "show stat" | socat stdio /var/run/haproxy.sock | grep <backend-name>
   # What to look for: status UP/DOWN, check status L7OK/L7STS
   ```

3. **Decision point:**
   - IF one slow backend holding connections → proceed to Mitigation Option A
   - IF legitimate traffic spike exceeding capacity → proceed to Mitigation Option B
   - IF maxconn too low for normal traffic → proceed to Mitigation Option C

## Mitigation

### Option A: Isolate slow backend

```bash
# Set weight to 0 (stop sending new traffic):
echo "set weight <backend>/<server> 0" | socat stdio /var/run/haproxy.sock
# Existing connections will drain. New traffic goes to other backends.
```

### Option B: Increase maxconn temporarily

```bash
# Runtime change (no restart needed):
echo "set maxconn frontend <frontend-name> 100000" | socat stdio /var/run/haproxy.sock
# Also increase per-backend limits:
echo "set maxconn server <backend>/<server> 1000" | socat stdio /var/run/haproxy.sock
```

### Option C: Reduce backend timeout (drop slow connections faster)

```bash
# This requires config file change + reload:
# In haproxy.cfg: timeout server 5s (for the slow backend)
# Then graceful reload:
haproxy -f /etc/haproxy/haproxy.cfg -sf $(pidof haproxy)
```

**After mitigation:** Monitor — scur dropping, queue clearing, 503s stopping.

## Verification

- [ ] `scur` below 70% of `slim`
- [ ] Backend queue depth: 0
- [ ] No 503 errors
- [ ] All backend health checks passing
- [ ] API latency at baseline

```bash
echo "show stat" | socat stdio /var/run/haproxy.sock | grep "FRONTEND" | awk -F, '{print "scur="$5,"slim="$6}'
# Expected: scur well below slim
echo "show stat" | socat stdio /var/run/haproxy.sock | grep "BACKEND" | awk -F, '{print $1,"qcur="$3}'
# Expected: qcur=0 for all backends
```

## Failure Signals

- Connections don't drain after isolating backend
- Other backends also becoming slow (cascading)
- Maxconn increase not taking effect (system ulimit)
- New backend servers also getting overwhelmed

**If any failure signal is present:** Escalate.

## Rollback

1. **Restore isolated backend:** `echo "set weight <backend>/<server> 100" | socat stdio /var/run/haproxy.sock`
2. **Revert maxconn:** `echo "set maxconn frontend <name> <original>" | socat stdio /var/run/haproxy.sock`

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| All backends slow (not isolated to one) | Platform + backend teams | PagerDuty P1 | Immediate |
| Cannot isolate slow backend | Network/infra team | #platform-support | 5 min |
| System ulimit preventing maxconn increase | Infra team | #platform-support | 10 min |
| Full LB outage (process crash) | EM + Platform Lead | PagerDuty P1 | Immediate |

## Notes

- **One slow backend can exhaust the entire LB.** Always set per-backend `maxconn` limits. See [[INC-033-haproxy-connection-pool-exhaustion]].
- **Runtime changes via stats socket don't survive restart.** Always update `haproxy.cfg` as permanent fix.
- **Backend timeout too high** (e.g., 60s) means one slow service can hold connections for a full minute. Keep timeouts tight.

## Maintenance

- **Last tested:** 2026-06-15
- **Review cycle:** Quarterly
- **Next review:** 2026-09-15
- **Test method:** Introduce artificial latency to a staging backend, verify connection pile-up detection and isolation.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-15 | SRE Team | Initial publication |
