---
title: Day 6 QA Checklist — Local LLM Verification
tags:
  - meta
  - qa
  - llm
  - testing
created: 2026-06-02
updated: 2026-06-02
type: reference
---

# Day 6 QA Checklist — Local LLM Verification with llama3.1

## Overview

This document provides a step-by-step verification plan to confirm that:

1. Days 1–5 of the Production Support Wiki are correctly in place.
2. Ollama is running locally with the `llama3.1` model.
3. Markdown notes from the vault can be loaded as context and queried.
4. The model produces answers grounded in the wiki content, not generic hallucination.

Execute each section in order. Record pass/fail for each item.

---

## Section 1: Prerequisites — Vault Integrity (Days 1–5)

### 1.1 Folder Structure

**What:** Confirm all top-level folders exist.

**How:**
```powershell
Get-ChildItem -Directory "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw"
```

**Pass:** Output contains: `Incidents`, `Runbooks`, `Templates`, `Indexes`, `Tests`, `Assets`
**Fail:** Any folder missing.

---

### 1.2 Incident Notes (INC-001 through INC-021)

**What:** Confirm at least 20 incident files exist with correct naming.

**How:**
```powershell
(Get-ChildItem "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw\Incidents\Active\*.md").Count
Get-ChildItem "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw\Incidents\Active\*.md" | Select-Object Name
```

**Pass:** Count ≥ 20. Files named `INC-001-...md` through `INC-021-...md` (or similar sequential).
**Fail:** Fewer than 20 files or naming convention broken.

---

### 1.3 Runbook Notes (RB-001 through RB-007)

**What:** Confirm 6–7 runbook files exist.

**How:**
```powershell
Get-ChildItem "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw\Runbooks\*.md" | Select-Object Name
```

**Pass:** At least 6 files: RB-001 (OOM), RB-002 (OOM generic), RB-003 (disk), RB-004 (CPU), RB-005 (DB), RB-006 (deployment), RB-007 (pod crash).
**Fail:** Missing runbooks.

---

### 1.4 Templates Exist

**What:** Confirm Incident Template and Runbook Template are present.

**How:**
```powershell
Get-ChildItem "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw\Templates\*.md" | Select-Object Name
```

**Pass:** Contains `Incident Template.md` and `Runbook Template.md`.
**Fail:** Either missing.

---

### 1.5 Index/Navigation Notes

**What:** Confirm navigation layer exists.

**How:**
```powershell
Get-ChildItem "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw\Indexes\*.md" | Select-Object Name
```

**Pass:** Contains at minimum: `Incident Index.md`, `Runbook Index.md`, `Category Navigation.md`, `Cross-Link Map.md`.
**Fail:** Any missing.

---

## Section 2: Ollama Environment

### 2.1 Ollama is Installed and Running

**What:** Confirm the Ollama process is active.

**How:**
```powershell
ollama --version
ollama list
```

**Pass:** `ollama --version` returns a version string (e.g., `0.1.x` or later). `ollama list` returns a table of models.
**Fail:** Command not found or Ollama not running.

---

### 2.2 llama3.1 Model is Available

**What:** Confirm `llama3.1` is pulled and ready.

**How:**
```powershell
ollama list
```

**Pass:** Output contains a row with `llama3.1` (any quantization: `llama3.1:latest`, `llama3.1:8b`, etc.).
**Fail:** `llama3.1` not in the list.

If not present, pull it:
```powershell
ollama pull llama3.1
```

---

### 2.3 Model Responds to Basic Prompt

**What:** Smoke test that the model accepts prompts and responds.

**How:**
```powershell
ollama run llama3.1 "What is Kubernetes? Answer in one sentence."
```

**Pass:** Returns a coherent one-sentence answer about Kubernetes.
**Fail:** Error, timeout, or garbage output.

---

### 2.4 HTTP API is Accessible

**What:** Confirm Ollama HTTP API on localhost:11434 is reachable.

**How (PowerShell):**
```powershell
Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get
```

**Pass:** Returns JSON with a `models` array containing `llama3.1`.
**Fail:** Connection refused or model not listed.

---

### 2.5 HTTP API Chat Endpoint Works

**What:** Confirm the `/api/chat` endpoint accepts messages and returns completions.

**How (PowerShell):**
```powershell
$body = @{
    model = "llama3.1"
    messages = @(
        @{ role = "user"; content = "Say hello in exactly 5 words." }
    )
    stream = $false
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -Body $body -ContentType "application/json"
```

**Pass:** Returns a JSON response with a `message.content` field containing a ~5-word greeting.
**Fail:** Error response, timeout, or empty content.

---

## Section 3: Retrieval Test — Wiki Context Injection

This is the core Day 6 test: feeding Markdown notes as context and verifying grounded answers.

### 3.1 Load Wiki Notes into a Prompt

**What:** Read 2–3 notes from the vault and pass them as system/context to llama3.1.

**How:** Create a test script. Save as `C:\Users\Dell\OneDrive\Desktop\LLMKB\test-retrieval.ps1`:

```powershell
# Read two wiki notes as context
$incident = Get-Content "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw\Incidents\Active\INC-001-payment-service-oom-crash.md" -Raw
$runbook = Get-Content "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw\Runbooks\RB-002-kubernetes-oom-remediation.md" -Raw

# Construct the prompt with wiki context
$systemPrompt = @"
You are an SRE assistant. Answer questions ONLY using the wiki context provided below.
If the answer is not in the context, say "Not found in wiki context."
Do not use your general knowledge — only the provided documents.

--- WIKI CONTEXT START ---
$incident

---

$runbook
--- WIKI CONTEXT END ---
"@

$userQuestion = "What are the first three diagnostic commands to run when a pod is OOMKilled, according to the runbook?"

$body = @{
    model = "llama3.1"
    messages = @(
        @{ role = "system"; content = $systemPrompt }
        @{ role = "user"; content = $userQuestion }
    )
    stream = $false
} | ConvertTo-Json -Depth 5

$response = Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -Body $body -ContentType "application/json"
Write-Host "`n--- MODEL RESPONSE ---"
Write-Host $response.message.content
```

Run it:
```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\Dell\OneDrive\Desktop\LLMKB\test-retrieval.ps1"
```

**Pass:** The response mentions specific commands from RB-002 such as:
- `kubectl get pods -n <namespace> -l app=<service-name>`
- `kubectl describe pod <pod-name> -n <namespace> | grep -A5 "Last State"`
- `kubectl top pods -n <namespace>`

**Fail:** Response gives generic OOM advice not found in the runbook, or says "Not found in wiki context" when the answer IS there, or hallucinates commands not in the document.

---

### 3.2 Verify Grounding — Anti-Hallucination Check

**What:** Ask about something that IS NOT in the provided context and confirm the model does not fabricate an answer.

**How:** Modify the user question in the script above to:

```
"According to the wiki context, what is the procedure for handling a Redis cache eviction storm?"
```

(No Redis runbook is provided in context.)

**Pass:** Model responds with something like "Not found in wiki context" or "The provided documents do not contain information about Redis cache eviction."
**Fail:** Model invents a Redis procedure not present in the provided notes.

---

### 3.3 Incident-Specific Retrieval Test

**What:** Ask a question that can only be answered by the incident note (not the runbook).

**How:** Using the same script structure, ask:

```
"What was the confirmed root cause of INC-001, and how long was the outage?"
```

**Pass:** Response includes:
- Root cause: "Unbounded IdempotencyCache in TransactionBatchProcessor.java" (or equivalent wording)
- Duration: "47 minutes"

**Fail:** Generic answer about OOM without the specific cache name, or wrong duration.

---

### 3.4 Cross-Referencing Test

**What:** Ask a question that requires connecting information across both documents.

**How:** Ask:

```
"Based on the wiki context, if I follow the OOM runbook and increase memory limits but the pod is still growing toward the new limit, what should I do next?"
```

**Pass:** Response references "Option B: Rollback to last known good version" from RB-002 (or equivalent). May also reference "proceed to escalation" or "schedule root cause investigation."
**Fail:** Generic advice not from the runbook text.

---

### 3.5 Multi-Document Test (3 files)

**What:** Load a third document (e.g., RB-003-disk-space-full or INC-006-disk-full-db-volume) and ask about disk issues to verify the model can handle broader context.

**How:** Add a third file to the context in the script:

```powershell
$diskRunbook = Get-Content "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw\Runbooks\RB-003-disk-space-full.md" -Raw
```

Append it to `$systemPrompt` context block. Ask:

```
"A Postgres database volume is at 100% and writes are failing. According to the wiki, what are the two fastest actions to free space?"
```

**Pass:** Response includes:
- Drop stale replication slot (`pg_drop_replication_slot`)
- And/or VACUUM on bloated tables
- And/or truncate WAL by removing slot

All from the RB-003 or INC-006 content.

**Fail:** Generic Postgres advice not matching the provided wiki text.

---

## Section 4: Example Questions for Day 6 Testing

Use these exact questions in your retrieval tests. They are designed to require wiki-specific content:

### Question 1 (OOM — Runbook)
> "According to the wiki runbook, what are the three mitigation options (A, B, C) for an OOMKilled pod?"

**Expected grounded answer:** Option A = increase memory limit, Option B = rollback to known good version, Option C = scale horizontally.

### Question 2 (Incident — Specifics)
> "In incident INC-007, what was the root cause of high CPU and what regex was involved?"

**Expected grounded answer:** Catastrophic regex backtracking in `CardValidator.validateNumber()`, regex was `^([0-9]{4}[\s-]?){3}[0-9]{4}$`.

### Question 3 (DB Runbook — Commands)
> "What psql command does the wiki recommend to identify long-running queries causing timeouts?"

**Expected grounded answer:** The specific `SELECT pid, usename, state, ... FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '5 seconds'` query from RB-005.

### Question 4 (Deployment — Decision Tree)
> "According to the deployment rollback runbook, what must you check BEFORE rolling back if the deploy included a database migration?"

**Expected grounded answer:** Check if migration is backward-compatible; check if new columns are nullable; reference to INC-011.

### Question 5 (Negative/Anti-Hallucination)
> "What does the wiki say about handling a Kafka consumer lag incident?"

**Expected grounded answer:** "Not found in wiki context" or equivalent — there are no Kafka incidents in the provided notes.

---

## Section 5: Scoring Rubric

### Day 6 Fully Complete ✅

All of the following are true:
- [ ] Ollama running, `llama3.1` available and responding
- [ ] HTTP API accessible at localhost:11434
- [ ] At least 2–3 wiki notes successfully loaded as context into a prompt
- [ ] Model answers at least 3 out of 5 test questions with content clearly from the wiki (specific commands, specific values, specific names)
- [ ] Anti-hallucination test passes (model does NOT fabricate for out-of-context questions)
- [ ] A repeatable test script exists that can be re-run

### Day 6 Partially Complete ⚠️

- Ollama and llama3.1 are working
- Wiki notes can be loaded
- But model answers are partially grounded (mixes wiki content with generic knowledge)
- Or anti-hallucination test fails (model invents answers)
- Or only 1–2 test questions pass clearly

### Day 6 Not Complete ❌

Any of the following:
- Ollama not installed or llama3.1 not pulled
- Cannot load wiki notes into prompt
- Model never references specific wiki content in responses
- No test script or manual process documented
- Or using a model other than llama3.1

---

## Quick Reference: Key Commands

| Action | Command |
|--------|---------|
| Check Ollama version | `ollama --version` |
| List models | `ollama list` |
| Pull llama3.1 | `ollama pull llama3.1` |
| Interactive test | `ollama run llama3.1 "prompt"` |
| API health | `curl http://localhost:11434/api/tags` |
| API chat | `POST http://localhost:11434/api/chat` (JSON body with model + messages) |
| Read wiki file | `Get-Content "path\to\file.md" -Raw` |

---

## Appendix: Minimal Test Script (Copy-Paste Ready)

Save as `test-day6.ps1` and run with `powershell -ExecutionPolicy Bypass -File test-day6.ps1`:

```powershell
Write-Host "=== Day 6 QA: Local LLM Retrieval Test ===" -ForegroundColor Cyan

# Step 1: Check Ollama
Write-Host "`n[1/5] Checking Ollama..." -ForegroundColor Yellow
try {
    $models = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get
    $hasLlama = $models.models | Where-Object { $_.name -like "llama3.1*" }
    if ($hasLlama) {
        Write-Host "  PASS: llama3.1 found in Ollama" -ForegroundColor Green
    } else {
        Write-Host "  FAIL: llama3.1 not found. Run: ollama pull llama3.1" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  FAIL: Cannot reach Ollama API. Is it running?" -ForegroundColor Red
    exit 1
}

# Step 2: Load wiki context
Write-Host "`n[2/5] Loading wiki notes..." -ForegroundColor Yellow
$basePath = "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw"
$incidentFile = "$basePath\Incidents\Active\INC-001-payment-service-oom-crash.md"
$runbookFile = "$basePath\Runbooks\RB-002-kubernetes-oom-remediation.md"

if ((Test-Path $incidentFile) -and (Test-Path $runbookFile)) {
    $incident = Get-Content $incidentFile -Raw
    $runbook = Get-Content $runbookFile -Raw
    Write-Host "  PASS: Both files loaded" -ForegroundColor Green
} else {
    Write-Host "  FAIL: Wiki files not found at expected paths" -ForegroundColor Red
    exit 1
}

# Step 3: Grounded retrieval test
Write-Host "`n[3/5] Testing grounded retrieval..." -ForegroundColor Yellow
$systemPrompt = @"
You are an SRE assistant. Answer ONLY using the wiki context below.
If the answer is not in the context, say "Not found in wiki context."

--- WIKI CONTEXT ---
$incident

---

$runbook
--- END CONTEXT ---
"@

$body = @{
    model = "llama3.1"
    messages = @(
        @{ role = "system"; content = $systemPrompt }
        @{ role = "user"; content = "What was the confirmed root cause of INC-001 and how long was the outage?" }
    )
    stream = $false
} | ConvertTo-Json -Depth 5

$response = Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -Body $body -ContentType "application/json"
$answer = $response.message.content
Write-Host "  Answer: $answer" -ForegroundColor White

if ($answer -match "IdempotencyCache|idempotency" -and $answer -match "47") {
    Write-Host "  PASS: Answer grounded in wiki content" -ForegroundColor Green
} else {
    Write-Host "  WARN: Answer may not be fully grounded. Review manually." -ForegroundColor Yellow
}

# Step 4: Anti-hallucination test
Write-Host "`n[4/5] Anti-hallucination test..." -ForegroundColor Yellow
$body2 = @{
    model = "llama3.1"
    messages = @(
        @{ role = "system"; content = $systemPrompt }
        @{ role = "user"; content = "According to the wiki context, what is the procedure for a Kafka consumer lag incident?" }
    )
    stream = $false
} | ConvertTo-Json -Depth 5

$response2 = Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -Body $body2 -ContentType "application/json"
$answer2 = $response2.message.content
Write-Host "  Answer: $answer2" -ForegroundColor White

if ($answer2 -match "not found|not contain|no information|not mentioned|not in the") {
    Write-Host "  PASS: Model correctly refused to hallucinate" -ForegroundColor Green
} else {
    Write-Host "  WARN: Model may have hallucinated. Review answer above." -ForegroundColor Yellow
}

# Step 5: Runbook command retrieval
Write-Host "`n[5/5] Runbook command retrieval test..." -ForegroundColor Yellow
$body3 = @{
    model = "llama3.1"
    messages = @(
        @{ role = "system"; content = $systemPrompt }
        @{ role = "user"; content = "According to the runbook, what are the three mitigation options (A, B, C) for an OOMKilled pod?" }
    )
    stream = $false
} | ConvertTo-Json -Depth 5

$response3 = Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -Body $body3 -ContentType "application/json"
$answer3 = $response3.message.content
Write-Host "  Answer: $answer3" -ForegroundColor White

if ($answer3 -match "memory limit|increase" -and $answer3 -match "rollback|roll back" -and $answer3 -match "scale") {
    Write-Host "  PASS: All three mitigation options referenced" -ForegroundColor Green
} else {
    Write-Host "  WARN: Not all options found. Review answer." -ForegroundColor Yellow
}

Write-Host "`n=== Day 6 QA Complete ===" -ForegroundColor Cyan
Write-Host "Review WARN items manually. 3+ PASS = Day 6 complete." -ForegroundColor White
```

---

*End of Day 6 QA Checklist*
