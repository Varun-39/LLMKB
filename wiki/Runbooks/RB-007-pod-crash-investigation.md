---
id: RB-007
title: Pod Crash / CrashLoopBackOff Investigation and Fix
service: "*"
related_services:
  - api-gateway
  - auth-service
  - payment-service
  - reporting-service
severity: SEV-2
environment: prod
category: resource-exhaustion
risk_level: medium
estimated_duration: "20m"
approval_required: no
approver_role: N/A
tags:
  - runbook
  - kubernetes
  - crashloop
  - pod
  - container
  - prod
related_incidents:
  - "[[INC-003-k8s-crashloopbackoff-auth]]"
related_runbooks:
  - "[[RB-002-kubernetes-oom-remediation]]"
  - "[[RB-003-disk-space-full]]"
  - "[[RB-006-failed-deployment-rollback]]"
related_guardrails: []
---

## Purpose

Triage and resolve pod crashes (CrashLoopBackOff, Error, ImagePullBackOff) on any Kubernetes service by identifying the crash category and routing to the appropriate fix or specialized runbook.

**Desired outcome:** All pods in `Running` state with 0 restarts in last 10 minutes, service healthy.

## Success Criteria

Before closing the incident or declaring the runbook complete, ALL of the following must be true:

- All pods in `Running` state with stable restart count (0 new restarts in 10 min)
- Application health endpoint returning 200
- Error rate at baseline in Grafana/APM
- No new crash events in `kubectl get events`
- No DiskPressure, MemoryPressure, or NotReady conditions on the pod's node

## Scope

| Attribute | Value |
|-----------|-------|
| Service | Any Kubernetes service with crashing pods |
| Related services | api-gateway, auth-service, payment-service, reporting-service |
| Environments | prod, staging |
| Use when | `*-PodCrashLooping`, `*-PodNotReady`, or `*-PodRestartHigh` alert, or pods in CrashLoopBackOff/Error/ImagePullBackOff |
| Do NOT use when | Pod is in `Pending` state only (use resource capacity runbook instead) |
| Risk level | Medium |
| Estimated duration | 15–20 minutes |
| Approval required | No |

## Prerequisites

- [ ] `kubectl` access to affected cluster and namespace
- [ ] Identify which service/pod is crashing (from alert payload)
- [ ] Access to Grafana and application logs
- [ ] Determine if this is a new deployment or an existing pod that started crashing

## Required Tools

| Tool | Purpose | Access Level |
|------|---------|-------------|
| `kubectl` | Pod inspection, logs, exec | Cluster admin |
| Grafana | Error rate and resource metrics | Read access |
| Sentry/APM | Application error context | Read access |
| Container registry | Image inspection and tag verification | Read access |

## Trigger

- Alert: `*-PodCrashLooping`, `*-PodNotReady`, or `*-PodRestartHigh`
- Symptom: `kubectl get pods` shows `CrashLoopBackOff`, `Error`, `ImagePullBackOff`, or restart count climbing
- Symptom: Kubernetes event `Back-off restarting failed container`
- Symptom: Service degradation correlated with pod restart count

## Triage

1. Get pod status and restart count
   ```bash
   kubectl get pods -n <namespace> -l app=<service-name>
   # What to look for: STATUS column (CrashLoopBackOff, Error, ImagePullBackOff) and RESTARTS count
   ```

2. Describe the pod for events and exit reason
   ```bash
   kubectl describe pod <pod-name> -n <namespace>
   # What to look for:
   # - Last State → Reason (OOMKilled, Error, ContainerCannotRun)
   # - Exit Code (137 = OOM/SIGKILL, 1 = app error, 2 = shell error)
   # - Events → scheduling, pulling, or startup failures
   ```

3. Quick classification:

   | Exit Code / Reason | Likely Cause | Next Step |
   |--------------------|--------------|-----------|
   | `OOMKilled` (exit 137) | Memory limit hit | → Use [[RB-002-kubernetes-oom-remediation]] |
   | `Error` (exit 1) | Application startup failure | → Check logs for exception |
   | `ContainerCannotRun` | Missing binary, bad entrypoint | → Check image and Dockerfile |
   | `ImagePullBackOff` | Image not found or auth failed | → Check image tag + registry creds |
   | `RunContainerError` | Security context, volume mount | → Check pod spec permissions |
   | `Pending` (not crashing) | Insufficient resources | → Check node capacity |

## Investigation

1. **Get logs from the crashed container**
   ```bash
   kubectl logs <pod-name> -n <namespace> --tail=200
   kubectl logs <pod-name> -n <namespace> --previous --tail=200
   # For multi-container pods:
   kubectl logs <pod-name> -n <namespace> -c <container-name> --previous
   ```

2. **Check if deployment-related**
   ```bash
   kubectl rollout history deployment/<deployment> -n <namespace>
   # What to look for: crash started after new revision = likely bad deploy
   # Crash on long-running pod = runtime issue
   ```

3. **Check Secret/ConfigMap issues**
   ```bash
   kubectl describe pod <pod-name> -n <namespace> | grep -A5 "Mounts"
   # What to look for: empty values, malformed encoding, wrong secret referenced
   ```

4. **Check node health**
   ```bash
   kubectl get nodes -o wide
   kubectl describe node <node-where-pod-runs> | grep -A10 "Conditions"
   # What to look for: NotReady, DiskPressure, MemoryPressure = node issue, not app issue
   ```

5. **Check resource availability** (for Pending pods)
   ```bash
   kubectl describe pod <pod-name> -n <namespace> | grep -A5 "Events"
   # What to look for: "0/N nodes are available: insufficient cpu/memory"
   kubectl top nodes
   ```

6. **Decision point:**
   - IF OOMKilled → hand off to [[RB-002-kubernetes-oom-remediation]]
   - IF application error (exit 1) → proceed to Mitigation: Application Error
   - IF bad Secret/ConfigMap → proceed to Mitigation: Secret/ConfigMap Fix
   - IF ImagePullBackOff → proceed to Mitigation: Image Pull Fix
   - IF deployment-related → proceed to Mitigation: Rollback
   - IF node-level issue → proceed to Mitigation: Node Issue
   - IF unclear → escalate (see Escalation section)

## Mitigation

### If OOMKilled → Use [[RB-002-kubernetes-oom-remediation]]

### Application error (exit code 1)

```bash
# Common causes: failed DB connection, missing env var, broken config
# Fix the underlying cause, then:
kubectl rollout restart deployment/<deployment> -n <namespace>
```

### Bad Secret/ConfigMap (e.g., base64 error)

```bash
kubectl patch secret <secret-name> -n <namespace> \
  --type='json' -p='[{"op":"replace","path":"/data/<key>","value":"<correct-base64>"}]'
kubectl rollout restart deployment/<deployment> -n <namespace>
```

### ImagePullBackOff

```bash
# Check if image tag exists:
aws ecr describe-images --repository-name <repo> --image-ids imageTag=<tag>
# IF tag doesn't exist → fix image reference:
kubectl set image deployment/<deployment> -n <namespace> \
  <container>=<correct-image:tag>
# IF auth issue → regenerate ECR secret (see RB-006 Scenario F)
```

### Deployment-related → rollback

```bash
kubectl rollout undo deployment/<deployment> -n <namespace>
kubectl rollout status deployment/<deployment> -n <namespace> --timeout=180s
```

### Node-level issue (DiskPressure, MemoryPressure, NotReady)

```bash
# Cordon the bad node and let pods reschedule:
kubectl cordon <node-name>
kubectl delete pod <pod-name> -n <namespace>
# Pod will be rescheduled to a healthy node
# Investigate node separately (SSH, systemctl status kubelet)
```

**After mitigation:** Monitor for 10 minutes — restart count stable, health endpoint returning 200, no new crash events.

## Verification

- [ ] All pods in `Running` state
- [ ] Restart count not increasing (stable for 10 min)
- [ ] Application health endpoint returning 200
- [ ] Error rate at baseline in Grafana/APM
- [ ] No new crash events in `kubectl get events -n <namespace>`

```bash
kubectl get pods -n <namespace> -l app=<service-name>
# Expected: STATUS=Running, RESTARTS stable
kubectl get events -n <namespace> --sort-by='.lastTimestamp' | tail -10
# Expected: no new CrashLoopBackOff or OOMKilled events
curl -s -o /dev/null -w "%{http_code}" https://<service-endpoint>/health
# Expected: 200
```

## Failure Signals

If the mitigation did NOT work, you will observe one or more of the following:

- Pod restart count continues to climb after fix applied
- Same error reappears in logs after restart
- Pod scheduled to new node still crashes (not a node issue)
- Multiple pods across different services begin crashing (systemic issue)
- Health endpoint remains non-200 after 5 minutes

**If any failure signal is present after mitigation:** Do NOT repeat the same step. Proceed to Rollback or Escalation immediately.

## Rollback

If your mitigation introduced new problems:

1. **Undo deployment rollback:**
   ```bash
   kubectl rollout undo deployment/<deployment> -n <namespace>
   ```

2. **Undo secret/configmap fix:**
   ```bash
   kubectl patch secret <secret-name> -n <namespace> \
     --type='json' -p='[{"op":"replace","path":"/data/<key>","value":"<original-base64>"}]'
   ```

3. **Uncordon node if cordoned:**
   ```bash
   kubectl uncordon <node-name>
   ```

4. Notify #incident-response: "Rollback executed — escalating."

## Escalation

| Trigger | Escalate To | Channel | SLA |
|---------|-------------|---------|-----|
| Pod keeps crashing after 3 mitigation attempts | Service owner | Direct page | 5 min response |
| Node-level issue affecting multiple services | Platform/SRE team | #platform-support | 10 min response |
| Crash cause unclear after 20 min investigation | Senior on-call + EM | PagerDuty escalation | 5 min response |
| Image/registry issue cluster-wide | Platform team | #platform-support | 10 min response |
| Data integrity concern (pod crashed mid-write) | DBA team | #data-eng | Immediate |

## Notes

- **CrashLoopBackOff backoff timing:** K8s backs off restarts exponentially (10s, 20s, 40s, 80s, up to 5 min). If you need the pod to retry sooner, delete it manually: `kubectl delete pod <name>`.
- **Exit code 137 is always OOM or external SIGKILL.** Don't troubleshoot application code for exit 137 — go straight to [[RB-002-kubernetes-oom-remediation]].
- **Secret encoding errors** are a top-3 crash cause in this environment. Base64 encoding with trailing newlines causes failures. See [[INC-003-k8s-crashloopbackoff-auth]].
- **Liveness probe failures** can cause restarts that look like crashes. Check `kubectl describe pod` for liveness probe failure events before assuming the application is buggy.
- **Init containers** can cause pods to fail before the main container starts. Check init container logs: `kubectl logs <pod> -n <ns> -c <init-container> --previous`.
- **This is a triage runbook.** After identifying the crash category, hand off to the specific runbook: [[RB-002-kubernetes-oom-remediation]], [[RB-003-disk-space-full]], [[RB-006-failed-deployment-rollback]].
- See also: [[INC-003-k8s-crashloopbackoff-auth]], [[INC-012-k8s-imagepullbackoff-reports]]

## Maintenance

- **Last tested:** 2026-06-02
- **Review cycle:** Quarterly
- **Next review:** 2026-09-02
- **Test method:** Deploy a container with an invalid entrypoint in staging, execute runbook triage and fix steps.

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-02 | SRE Team | Initial publication |
| 2026-06-12 | SRE Team | Migrated to new runbook template format |
