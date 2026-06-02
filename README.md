# LLMKB — Obsidian Production Support Wiki with Local LLM

## Project Overview

LLMKB is a prototype of an LLM-assisted knowledge base for production support teams. It combines three layers:

- **Obsidian** as the wiki and documentation interface — structured Markdown notes with wikilinks, tags, YAML frontmatter, and Dataview dashboards.
- **Markdown files** as the knowledge base — incident notes, runbooks, templates, and navigation indexes, all human-readable and version-controllable.
- **Ollama + llama3.1** as the local LLM layer — enabling question answering grounded in wiki content without any cloud dependency.

The use case is straightforward: an on-call engineer or SRE can browse the wiki in Obsidian for structured documentation, or ask the local LLM natural-language questions about incidents and runbooks and receive answers sourced from the actual wiki content.

This project demonstrates that a lightweight, private, local-first knowledge retrieval workflow is achievable with open-source tools on a single Windows machine.

## Features

- **Obsidian-based Markdown knowledge base** — all content is plain Markdown with YAML frontmatter, fully portable and editable in any text editor
- **Synthetic production incident library** — 21 realistic incident notes covering Kubernetes, infrastructure, database, and deployment failures
- **Practical runbooks** — 7 step-by-step runbooks for common operational issues (OOM, disk full, high CPU, DB timeouts, failed deployments, pod crashes)
- **Wiki navigation** — Dataview-powered indexes, category navigation, cross-link maps, and tag-based browsing
- **Consistent metadata schema** — every note has structured YAML frontmatter queryable by Dataview
- **Local LLM question answering** — load wiki notes as context and ask questions via Ollama's API using llama3.1
- **Private and local workflow** — no data leaves your machine, no API keys, no cloud services required
- **Templates** — reusable incident and runbook templates with placeholder values for fast note creation

## Project Structure

```
LLMKB/
├── raw/                          # Obsidian vault root
│   ├── Incidents/
│   │   ├── Active/               # 21 incident notes (INC-001 to INC-021)
│   │   └── Resolved/            # Closed incidents (moved here on resolution)
│   ├── Runbooks/                 # 7 operational runbooks (RB-001 to RB-007)
│   ├── Templates/                # Incident and Runbook templates
│   ├── Indexes/                  # Dataview dashboards and navigation
│   │   ├── Incident Index.md
│   │   ├── Runbook Index.md
│   │   ├── Category Navigation.md
│   │   └── Cross-Link Map.md
│   ├── Tests/                    # Test scenarios and QA checklists
│   ├── Assets/                   # Diagrams and screenshots
│   ├── Production Support Wiki.md   # Homepage
│   ├── Plugin Setup Guide.md
│   └── Day 2 - Conventions and Usage Guide.md
├── test-retrieval.ps1            # PowerShell script for LLM retrieval testing
└── README.md                     # This file
```

## Requirements

| Requirement | Details |
|-------------|---------|
| **Obsidian** | Latest version — [download](https://obsidian.md/) |
| **Ollama** | Latest version — [download](https://ollama.com/) |
| **llama3.1** | Pulled via Ollama (8B parameter model, ~4.7 GB) |
| **PowerShell** | Version 5.1+ (included with Windows 10/11) |
| **System** | Windows 10/11, minimum 8 GB RAM (16 GB recommended for comfortable LLM inference) |
| **Dataview plugin** | Install from Obsidian Community Plugins for dashboard functionality |

## Setup Instructions

### 1. Get the project files

Clone or copy the `LLMKB` folder to your local machine.

### 2. Install Obsidian

Download and install from [obsidian.md](https://obsidian.md/).

### 3. Install and start Ollama

Download and install from [ollama.com](https://ollama.com/). After installation, Ollama runs as a background service automatically.

Verify it is running:

```powershell
ollama --version
```

### 4. Pull the llama3.1 model

```powershell
ollama pull llama3.1
```

This downloads the 8B parameter model (~4.7 GB). Wait for the download to complete.

### 5. Verify the model works

```powershell
ollama run llama3.1 "What is Kubernetes? Answer in one sentence."
```

You should receive a coherent one-sentence answer.

## How to Open the Wiki

1. Open Obsidian
2. Click **"Open folder as vault"**
3. Navigate to and select the `raw` folder:
   ```
   C:\Users\Dell\OneDrive\Desktop\LLMKB\raw
   ```
4. When prompted, trust the vault and enable community plugins
5. Install the **Dataview** plugin from Community Plugins (required for index dashboards)

Once open, you can:

- Start at **Production Support Wiki.md** (the homepage)
- Browse incidents in `Incidents/Active/`
- Read runbooks in `Runbooks/`
- Use the indexes in `Indexes/` for filtered Dataview tables
- Create new notes using templates from `Templates/`
- Use the graph view to visualize connections between incidents and runbooks

## How to Run the Retrieval Test

The project includes a PowerShell script that tests the local LLM's ability to answer questions grounded in wiki content.

### Run the script

```powershell
cd C:\Users\Dell\OneDrive\Desktop\LLMKB
powershell -ExecutionPolicy Bypass -File ".\test-retrieval.ps1"
```

### What the script does

1. Reads two Markdown files from the vault (an incident note and a runbook)
2. Injects their full content as context into the LLM prompt
3. Sends three questions to llama3.1 via Ollama's `/api/chat` endpoint
4. Prints the model's answers for manual verification

The test validates that the LLM's responses are grounded in the provided wiki content rather than hallucinated from general knowledge.

## Example Questions to Ask the LLM

These questions can be used with the retrieval test or adapted for your own testing:

**Grounded questions (answers should come from wiki content):**

- What are the first checks for an OOMKilled Kubernetes pod?
- What was the confirmed root cause of INC-001 and how long was the outage?
- According to the runbook RB-002, what are the three mitigation options (A, B, C) for an OOMKilled pod?
- What does the wiki say about disk space full on a database volume?
- What is the rollback procedure for a failed Kubernetes deployment?
- What caused the auth-service CrashLoopBackOff in INC-003?
- What are the escalation criteria if a database connection pool is exhausted?

**Anti-hallucination test (answer should be "not found in the provided documents"):**

- What does the wiki say about Kafka consumer lag incidents?

If the model answers the Kafka question with specific details, it is hallucinating — the wiki contains no Kafka-related incidents.

## How the Local LLM Workflow Works

The retrieval workflow is deliberately simple:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Select 2–3     │     │  Build prompt:   │     │  Send to Ollama  │
│  Markdown notes │ ──▶ │  system context  │ ──▶ │  /api/chat       │
│  from vault     │     │  + user question │     │  (llama3.1)      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  Inspect answer: │
                                                 │  grounded in     │
                                                 │  wiki content?   │
                                                 └─────────────────┘
```

1. **Select notes** — choose the incident or runbook files relevant to your question
2. **Inject as context** — the full Markdown content becomes the system message in the chat prompt
3. **Ask a question** — the user message contains your natural-language question
4. **Inspect the answer** — verify the response references specific details from the provided notes (dates, commands, root causes) rather than generic knowledge

This is a manual retrieval approach. The human selects which notes to load. A production system would automate this with embeddings and vector search.


## Usage Notes

- **This is a prototype/demo project.** The incident data is synthetic and the LLM integration is minimal by design.
- **Always verify LLM responses against the source notes.** Local LLMs can still hallucinate, especially when context is large or questions are ambiguous.
- **The workflow is local-first and privacy-friendly.** No data is sent to external services. All processing happens on your machine via Ollama.
- **Obsidian is optional for the LLM workflow.** The retrieval script reads Markdown files directly — you don't need Obsidian open to run the LLM test. Obsidian provides the browsing and navigation experience.
- **Model performance depends on hardware.** On systems with limited RAM, llama3.1 inference may be slow. Consider using a smaller model (e.g., `llama3.2:3b`) if response times are unacceptable.
