# test-retrieval.ps1
# Reads two Markdown files from the vault, sends them as context to Ollama,
# and asks questions using the /api/chat endpoint.

$ErrorActionPreference = "Stop"

# --- File paths ---
$incidentFile = "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw\Incidents\Active\INC-001-payment-service-oom-crash.md"
$runbookFile  = "C:\Users\Dell\OneDrive\Desktop\LLMKB\raw\Runbooks\RB-002-kubernetes-oom-remediation.md"

# --- Read file contents ---
$incidentContent = Get-Content -Path $incidentFile -Raw -Encoding UTF8
$runbookContent  = Get-Content -Path $runbookFile -Raw -Encoding UTF8

# --- Build context string ---
$context = @"
You are a production support assistant. Use ONLY the following documents to answer questions.

=== DOCUMENT 1: Incident Note ===
$incidentContent

=== DOCUMENT 2: Runbook ===
$runbookContent

=== END OF DOCUMENTS ===
Answer questions based strictly on the content above. Be concise and specific.
"@

# --- Ollama endpoint ---
$ollamaUrl = "http://localhost:11434/api/chat"

# --- Helper function ---
function Ask-Ollama {
    param(
        [Parameter(Mandatory)][string]$Question
    )

    $payload = @{
        model  = "llama3.1"
        stream = $false
        messages = @(
            @{ role = "system"; content = $context },
            @{ role = "user";   content = $Question }
        )
    }

    $json = $payload | ConvertTo-Json -Depth 10 -Compress

    Write-Host "`n-----------------------------------------------------------" -ForegroundColor Cyan
    Write-Host "Q: $Question" -ForegroundColor Yellow
    Write-Host "-----------------------------------------------------------" -ForegroundColor Cyan

    try {
        $response = Invoke-RestMethod -Uri $ollamaUrl -Method POST -Body $json -ContentType "application/json; charset=utf-8"
        $answer = $response.message.content
        Write-Host "A: $answer" -ForegroundColor Green
    }
    catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        if ($_.ErrorDetails.Message) {
            Write-Host "Detail: $($_.ErrorDetails.Message)" -ForegroundColor Red
        }
    }
}

# --- Ask questions ---
Write-Host "`n=== Ollama Retrieval Test ===" -ForegroundColor Magenta
Write-Host "Model: llama3.1"
Write-Host "Context: INC-001 + RB-002`n"

Ask-Ollama "What was the confirmed root cause of INC-001 and how long was the outage?"

Ask-Ollama "According to the runbook RB-002, what are the three mitigation options (A, B, C) for an OOMKilled pod? List them briefly."

Ask-Ollama "If a pod is still growing toward the new memory limit after Option A, what does the runbook say to do next?"

Write-Host "`n=== Test Complete ===" -ForegroundColor Magenta
