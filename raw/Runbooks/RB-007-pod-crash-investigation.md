<!-- File: RB-007-pod-crash-investigation.md -->
---
id: RB-007
title: Pod Crash / CrashLoopBackOff Investigation and Fix
service_scope: all services
environment_scope: prod, staging
owner: SRE Team
severity_scope: high, critical
tags:
  - runbook
  - kubernetes
  - crashloop
  - pod
  - container
  - prod
created: 2026-06-02
updated: 2026-06-02
related_incidents:
  - "[[INC-003-k8s-crashloopbackoff-auth]]"
  - "[[INC-004-k8s-node-notready]]"
  - "[[INC-012-k8s-imagepullbackoff-reports]]"
  - "[[INC-013-k8s-pending-pods-resource-pressure]]"
  - "[[INC-014-k8s-node-disk-pressure]]"
  - "[[INC-016-memory-pressure-app-node]]"
---

# Pod Crash / CrashLoopBackOff Investigation and Fix

## Trigger

- PagerDuty alert: `*-PodCrashLooping`, `*-PodNotReady`, or `*-PodRestartHigh`
- `kubectl get pods` shows pod status: `CrashLoopBackOff`, `Error`, `ImagePullBackOff`, or restart count climbing
- Kubernetes event: `Back-off restarting failed container`
- Service degradation correlated with pod restart count

**Desired outcome:** All pods in `Running` state with 0 restarts in last 10 minutes, service healthy.

## Preconditions

- [ ] `kubectl` access to affected cluster and namespace
- [ ] Identify which service/pod is crashing (from alert payload)
- [ ] Access to Grafana and application logs
- [ ] Determine if this is a new deployment or an existing pod that started crashing

**Required tools:** kubectl, Grafana, Sentry/APM, container registry access (for image inspection)

## Commands and Checks

### 1. Get pod status and restart count

```bash
kubectl get pods -n <namespace> -l app=<service-name>
# Note: STATUS column and RESTARTS count
# CrashLoopBackOff = container keeps exiting, K8s backs off restarts
```

### 2. Describe the pod for events and exit reason

```bash
kubectl describe pod <pod-name> -n <namespace>
# Key sections to check:
# - Last State → Reason (OOMKilled, Error, ContainerCannotRun)
# - Exit Code (137 = OOM/SIGKILL, 1 = application error, 2 = shell error)
# - Events → look for scheduling, pulling, or startup failures
```

### 3. Get logs from the crashed container

```bash
# Current (if briefly running):
kubectl logs <pod-name> -n <namespace> --tail=200
# Previous crash instance:
kubectl logs <pod-name> -n <namespace> --previous --tail=200
# IF multi-container pod, specify container:
kubectl logs <pod-name> -n <namespace> -c <container-name> --previous
```

### 4. Determine the crash category

| Exit Code / Reason | Likely Cause | Next Step |
|--------------------|--------------|-----------|
| `OOMKilled` (exit 137) | Memory limit hit | → Use [[RB-002-kubernetes-oom-remediation]] |
| `Error` (exit 1) | Application startup failure | → Check logs for exception |
| `ContainerCannotRun` | Missing binary, bad entrypoint | → Check image and Dockerfile |
| `ImagePullBackOff` | Image not found or auth failed | → Check image tag + registry creds |
| `RunContainerError` | Security context, volume mount | → Check pod spec permissions |
| `Pending` (not crashing) | Insufficient resources | → Check node capacity |

### 5. Check if it's deployment-related

```bash
kubectl rollout history deployment/<deployment> -n <namespace>
# IF crash started immediately after a new revision → likely bad deploy
# IF pods were running fine for days and started crashing → runtime issue
```

### 6. Check if it's a Secret/ConfigMap issue

```bash
kubectl describe pod <pod-name> -n <namespace> | grep -A5 "Mounts"
kubectl get secret <secret-name> -n <namespace> -o jsonpath='{.data}' | base64 -d
# Look for: empty values, malformed encoding, wrong secret referenced
```

### 7. Check node health (maybe the node is the problem)

```bash
kubectl get nodes -o wide
kubectl describe node <node-where-pod-runs> | grep -A10 "Conditions"
# IF node is NotReady or has DiskPressure/MemoryPressure → node issue, not app issue
```

### 8. Check resource availability (Pending pods)

```bash
kubectl describe pod <pod-name> -n <namespace> | grep -A5 "Events"
# Look for: "0/N nodes are available: insufficient cpu/memory"
kubectl top nodes
# IF all nodes at capacity → scale cluster or kill lower-priority workloads
```

## Mitigation

### If OOMKilled → Use [[RB-002-kubernetes-oom-remediation]]

### If application error (exit code 1)

```bash
# Check logs for the specific exception/error
kubectl logs <pod-name> -n <namespace> --previous --tail=100
# Common causes:
# - Failed DB connection on startup → check DB health
# - Missing env var or secret → check ConfigMap/Secret
# - Broken config file → check ConfigMap content
# Fix the underlying cause, then:
kubectl rollout restart deployment/<deployment> -n <namespace>
```

### If bad Secret/ConfigMap (e.g., base64 error)

```bash
# Fix the secret:
kubectl patch secret <secret-name> -n <namespace> \
  --type='json' -p='[{"op":"replace","path":"/data/<key>","value":"<correct-base64>"}]'
# Restart pods to pick up corrected secret:
kubectl rollout restart deployment/<deployment> -n <namespace>
```

### If ImagePullBackOff

```bash
# Check if image tag exists:
aws ecr describe-images --repository-name <repo> --image-ids imageTag=<tag>
# IF tag doesn't exist → wrong tag deployed, fix image reference
# IF auth issue → regenerate ECR secret (see RB-006 Scenario F)
kubectl set image deployment/<deployment> -n <namespace> \
  <container>=<correct-image:tag>
```

### If deployment-related → rollback

```bash
kubectl rollout undo deployment/<deployment> -n <namespace>
kubectl rollout status deployment/<deployment> -n <namespace> --timeout=180s
```

### If node-level issue (DiskPressure, MemoryPressure, NotReady)

```bash
# Cordon the bad node and let pods reschedule:
kubectl cordon <node-name>
kubectl delete pod <pod-name> -n <namespace>
# Pod will be rescheduled to a healthy node
# Investigate node separately (SSH, systemctl status kubelet, etc.)
```

## Verification

- [ ] All pods in `Running` state
- [ ] Restart count not increasing (stable for 10 min)
- [ ] Application health endpoint returning 200
- [ ] Error rate at baseline in Grafana/APM
- [ ] No new crash events in `kubectl get events -n <namespace>`

```bash
kubectl get pods -n <namespace> -l app=<service-name>
# Verify: STATUS=Running, RESTARTS stable
kubectl get events -n <namespace> --sort-by='.lastTimestamp' | tail -10
# Verify: no new CrashLoopBackOff or OOMKilled events
curl -s -o /dev/null -w "%{http_code}" https://<service-endpoint>/health
# Expect: 200
```

## Rollback

If your mitigation introduced new problems:

```bash
# Undo deployment rollback:
kubectl rollout undo deployment/<deployment> -n <namespace>

# Undo secret/configmap fix:
kubectl patch secret <secret-name> -n <namespace> \
  --type='json' -p='[{"op":"replace","path":"/data/<key>","value":"<original-base64>"}]'

# Uncordon node if cordoned:
kubectl uncordon <node-name>
```

## Escalation

| Condition | Escalate to | Channel |
|-----------|-------------|---------|
| Pod keeps crashing after 3 mitigation attempts | Service owner | Direct page |
| Node-level issue affecting multiple services | Platform/SRE team | #platform-support |
| Crash cause is unclear after 20 min investigation | Senior on-call + EM | PagerDuty escalation |
| Image/registry issue cluster-wide | Platform team | #platform-support |
| Data integrity concern (pod crashed mid-write) | DBA team | #data-eng |

## Notes / Gotchas

- **CrashLoopBackOff backoff timing:** K8s backs off restarts exponentially (10s, 20s, 40s, 80s, up to 5 min). If you need the pod to retry sooner, delete it manually: `kubectl delete pod <name>`.
- **Exit code 137 is always OOM or external SIGKILL.** Don't troubleshoot application code for exit 137 — go straight to the OOM runbook [[RB-002-kubernetes-oom-remediation]].
- **Secret encoding errors** are a top-3 crash cause in this environment. Base64 encoding with trailing newlines causes failures. See [[INC-003-k8s-crashloopbackoff-auth]].
- **Liveness probe failures** can cause restarts that look like crashes. Check `kubectl describe pod` for liveness probe failure events before assuming the application is buggy.
- **Init containers** can cause pods to fail before the main container starts. Check init container logs: `kubectl logs <pod> -n <ns> -c <init-container> --previous`.
- **This is a triage runbook.** After identifying the crash category, hand off to the specific runbook: [[RB-002-kubernetes-oom-remediation]], [[RB-003-disk-space-full]], [[RB-006-failed-deployment-rollback]].
