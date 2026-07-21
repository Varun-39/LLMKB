# LLMKB — Operational Knowledge Base with RAG

A structured operational knowledge base (incidents, runbooks, system docs) powered by a Retrieval-Augmented Generation pipeline using **LlamaIndex**, **Ollama**, **MinIO**, and **ChromaDB**.

Fully local. No API keys required. No data leaves your machine.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [API Server](#api-server)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Architecture

```
wiki/ (Obsidian)  →  MinIO (S3)  →  LlamaIndex Reader  →  SectionNodeParser  →  ChromaDB  →  Alert Query Engine
  edit here          storage         parse + metadata       ## split + context     vectors      fingerprint → LlamaIndex + Ollama
```

### Pipeline Components

| Layer | Technology | Role |
|-------|-----------|------|
| Document source | MinIO / local `wiki/` | S3-compatible object store for Markdown files |
| Loading | Custom `BaseReader` subclasses | Parse YAML frontmatter, normalize metadata |
| Chunking | Custom `SectionNodeParser` | Split at `##` headers with contextual retrieval prefix |
| Embedding | Ollama `nomic-embed-text` (768d) | Local embeddings via LlamaIndex `OllamaEmbedding` |
| Vector store | ChromaDB (persistent) | Cosine similarity search with metadata filters |
| Keyword search | In-memory BM25 | Full-corpus exact-term matching for IDs and rare tokens |
| Hybrid fusion | Reciprocal Rank Fusion (RRF) | Merges dense + BM25 candidate pools |
| Reranking | Cross-encoder (disabled by default) | `ms-marco-MiniLM-L-2-v2`; adds ~34s one-time load + ~1.3s/query for no measurable gain over the multi-signal scorer alone — toggle via `config/scoring.yaml`'s `reranker.enabled` |
| Multi-signal scoring | YAML-configured scorer | Weighted: RRF, exact match, metadata, section relevance, doc-type priority |
| Generation | Ollama `llama3.1` | Local LLM via LlamaIndex `Ollama` |
| Orchestration | LlamaIndex `RetrieverQueryEngine` | Chains retrieval → synthesis with custom SRE prompt |
| Delta tracking | SQLite manifest | SHA-256 hashing to skip unchanged files |
| Error fingerprinting | `src/fingerprint.py` | Deterministic alert → KB match key (no LLM); hashes top 3 in-app stack frames, not just the first |
| Recommendation cache | `src/recommendation_cache.py` | SQLite, keyed by fingerprint signature — repeat incidents skip retrieval + generation entirely |

---

## Prerequisites

- **Python 3.11+**
- **Ollama** installed and running ([install guide](https://ollama.com))
- **MinIO** binary (Windows: `C:\minio\minio.exe`, Linux/macOS: see [MinIO docs](https://min.io/docs/minio/linux/index.html))

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Varun-39/LLMKB.git
cd LLMKB
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Pull Ollama models

```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

### 4. Configure environment

```bash
# Windows
copy .env.example .env

# Linux/macOS
cp .env.example .env
```

Edit `.env` with your preferred settings (see [Configuration](#configuration)).

### 5. Start MinIO

```bash
# Windows
scripts\start_minio.bat
```

MinIO Console: http://localhost:9001 (default credentials: `minioadmin` / `minioadmin123`)

---

## Usage

### Sync documents to MinIO

```bash
python scripts/sync_to_minio.py

# Preview what would be uploaded without actually uploading
python scripts/sync_to_minio.py --dry-run
```

### Build the index

```bash
# From MinIO (production path):
python -m src.ingest

# From local wiki/ (dev shortcut, no MinIO needed):
python -m src.ingest --local

# Force full re-index (bypasses delta tracking):
python -m src.ingest --local --force

# With LLM keyword/summary extraction per chunk (slow, ~1–3s/node):
python -m src.ingest --local --extract-metadata
```

There is no free-text query CLI or API — the only way to get a recommendation is `POST /alert` (see below). `src/query.py` is a library module consumed by the alert pipeline, not a standalone tool.

---

## API Server

The FastAPI server loads the index once at startup — no cold-start penalty per request.

### Start the server

```bash
uvicorn src.server:app --host 127.0.0.1 --port 8000
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/alert` | Demo alert intake (synthetic Splunk-webhook JSON, see `data/sample_alerts/`) → fingerprint → grounded recommendation, cached by signature |
| `GET` | `/health` | ChromaDB + Ollama connectivity status |
| `POST` | `/ingest/refresh` | Re-index changed documents and reload |

### Alert intake (demo)

No live Splunk/ITRS integration yet — `/alert` takes a JSON payload shaped like a Splunk webhook alert action (see [`src/alerts.py`](src/alerts.py)). Sample payloads live in [`data/sample_alerts/`](data/sample_alerts):

```bash
curl -X POST http://localhost:8000/alert \
  -H "Content-Type: application/json" \
  -d @data/sample_alerts/alert-connection-pool-exhausted.json
```

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```ini
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
OLLAMA_EMBED_MODEL=nomic-embed-text

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
MINIO_BUCKET=llmkb
MINIO_SECURE=false

# ChromaDB
CHROMA_PERSIST_DIR=./chroma_db

# SQLite manifest
MANIFEST_DB=./manifest.db

# Wiki source directory
WIKI_SOURCE_DIR=./wiki
```

### Scoring (`config/scoring.yaml`)

All retrieval scoring parameters — no code changes needed to tune:

- **weights** — relative importance of RRF, exact match, metadata match, section relevance, and doc-type authority
- **penalties** — score deductions for low-value sections (`links`, `revision-history`)
- **thresholds** — ID-routing regex, candidate multiplier, RRF constant
- **intent_keywords** — classify query as "action" (fix/resolve/how) vs "info" (what/why/timeline)
- **doc_type_priority** — authority tier: `runbook` (1.0) > `incident` (0.75) > `system` (0.5) > `vendor-note` (0.2)
- **doc_coherence** — boost for documents with multiple chunks in the candidate pool
- **reranker** — toggle cross-encoder reranking and set model/top-n

### Fingerprinting (`config/fingerprint.yaml`)

Rules for deterministic error fingerprinting — no code changes needed:

- **volatile_patterns** — regex substitutions to strip timestamps, UUIDs, IPs, instance numbers before hashing
- **framework_frame_prefixes** — JVM/framework package prefixes to skip during stack trace root-frame extraction
- **error_families** — 23 pattern-to-family mappings keyed to runbook slugs (`connection-pool-exhausted`, `oom`, `disk-full`, etc.)

---

## Project Structure

```
LLMKB/
├── wiki/                        # Markdown knowledge base (Obsidian vault)
│   ├── Incidents/               # 100 incident reports (INC-001 – INC-100)
│   ├── Runbooks/                # 42 operational runbooks (RB-001 – RB-042)
│   ├── System/                  # 5 service architecture docs (SYS-001 – SYS-005)
│   ├── Governance/              # Escalation rules, guardrails
│   ├── Templates/               # Document templates (excluded from indexing)
│   └── Vendor notes/            # Third-party tooling notes
├── src/
│   ├── config.py                # Env config + LlamaIndex Settings init
│   ├── loader.py                # MinIO/local readers (LlamaIndex BaseReader)
│   ├── chunker.py               # SectionNodeParser: ## boundaries + contextual prefix
│   ├── indexer.py               # ChromaDB VectorStoreIndex management
│   ├── manifest.py              # SQLite delta tracking (SHA-256 per file)
│   ├── ingest.py                # Ingestion pipeline (load → parse → embed → store)
│   ├── retrieval.py             # BM25, RRF hybrid fusion, multi-signal scoring
│   ├── query.py                 # Query engine library (retrieve → rerank → generate), consumed by /alert
│   ├── server.py                # FastAPI server: /alert, /health, /ingest/refresh
│   ├── fingerprint.py           # Deterministic alert → signature_id (no LLM)
│   ├── alerts.py                # Splunk-webhook-shaped alert payload + query builder
│   └── recommendation_cache.py  # SQLite cache, keyed by fingerprint signature_id
├── config/
│   ├── scoring.yaml             # Retrieval scoring weights and tuning
│   └── fingerprint.yaml         # Fingerprint normalization + error family rules
├── scripts/
│   ├── sync_to_minio.py         # One-way wiki/ → MinIO sync
│   └── start_minio.bat          # Start MinIO server (Windows)
├── data/
│   └── sample_alerts/           # Sample Splunk-webhook-shaped alert JSON payloads
├── tests/
│   ├── test_fingerprint.py      # Fingerprint self-check (plain asserts)
│   ├── test_alerts.py           # Alert payload / query-builder tests
│   └── test_recommendation_cache.py  # Recommendation cache tests
├── chroma_db/                   # ChromaDB persistence (gitignored)
├── manifest.db                  # SQLite delta manifest (gitignored)
├── recommendations.db           # SQLite recommendation cache (gitignored)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## How It Works

### Loading (`src/loader.py`)

`MinIOMarkdownReader` and `LocalMarkdownReader` both parse YAML frontmatter from each `.md` file and normalize metadata into consistent fields (`doc_type`, `id`, `service`, `severity`, `tags`, `object_key`). Templates and `.obsidian` files are excluded automatically.

### Chunking with Contextual Retrieval (`src/chunker.py`)

`SectionNodeParser` splits documents at `##` header boundaries — never mid-section, so `Resolution` blocks always stay intact with all their steps. Each chunk gets a **contextual prefix** prepended before embedding:

```
This is the 'Resolution' section (resolution steps and commands used to fix the
issue) from incident report INC-009, related to payment-gateway service.
```

This situates the chunk within its parent document so the embedding captures both local content and document-level context, improving retrieval for queries that don't share exact wording with the chunk.

### Retrieval (`src/retrieval.py`)

Three paths depending on the query:

1. **ID routing** — queries like `INC-003` or `RB-001` match a regex and bypass all embedding. Direct ChromaDB metadata lookup, instant result.
2. **BM25 keyword search** — in-memory inverted index over the entire ChromaDB corpus. Catches exact-term matches (error codes, rare tokens, IDs mentioned in text) that dense retrieval misses.
3. **Hybrid fusion** — dense (cosine) candidates and BM25 candidates are unioned and merged via **Reciprocal Rank Fusion (RRF)**. BM25-only hits enter the pool even if they ranked outside the dense top-k.

### Scoring (`src/query.py`)

After the candidate pool is built, a **cross-encoder reranker** (optional, CPU-friendly) re-evaluates query-document pairs. Then `MultiSignalScorer` combines five signals with YAML-configured weights:

| Signal | What it measures |
|--------|-----------------|
| RRF score | Rank agreement between dense and BM25 retrieval |
| Exact match | IDF-weighted query token overlap with chunk text |
| Metadata match | Service mentioned in query matches `service` field |
| Section relevance | Section type matches query intent (action vs. info) |
| Doc-type priority | Authority tier: runbook > incident > system > informal |

A **document coherence boost** rewards documents with multiple chunks in the candidate pool. All signals and weights are in `config/scoring.yaml` — no code changes needed to tune.

### Delta Ingestion (`src/manifest.py`)

SQLite stores a SHA-256 hash per file. Subsequent `ingest` runs only re-embed files whose hash has changed. `--force` bypasses the manifest for a full rebuild.

### Error Fingerprinting (`src/fingerprint.py`)

Turns a raw alert/log line (+ optional JVM stack trace) into a stable `signature_id` (12-char SHA-256 prefix) without any LLM call. Pipeline:

1. Strip volatile fields (timestamps, UUIDs, IPs, instance numbers) using patterns from `config/fingerprint.yaml`
2. Extract the first non-framework application frame from a JVM stack trace
3. Classify into an error family (23 families, each keyed to a runbook slug)
4. Hash `family::service::anchor` → deterministic `signature_id`

Same error at different times, on different instances, collapses to the same ID. Different services never collide.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Cannot connect to Ollama" | Run `ollama serve` |
| "Model not found" | `ollama pull llama3.1` and `ollama pull nomic-embed-text` |
| "No relevant chunks found" | `python -m src.ingest --local --force` |
| MinIO connection refused | Run `scripts\start_minio.bat` |
| Slow first ingest | Normal — local embedding takes a few minutes. Delta runs are fast. |
| API server won't start | Build the index first: `python -m src.ingest --local` |
| Reranker not loading | Install optional deps: `pip install llama-index-postprocessor-sbert-rerank sentence-transformers` |
| ChromaDB process hangs after ingest | Expected — ChromaDB keeps background threads alive. The ingest script force-exits cleanly. |
| Generation takes 60-90s+ despite having a GPU | Run `ollama ps` during a query — if `PROCESSOR` shows a CPU/GPU split (e.g. `74%/26%`), the model's KV cache doesn't fit in VRAM. Check `context_window` in `src/config.py`'s `Ollama(...)` init isn't left at the LlamaIndex default (`-1`, which requests the model's full advertised context — 131072 for llama3.1). |

---

## Contributing

1. Fork the repository and create a feature branch.
2. Make your changes, keeping diffs minimal and focused.
3. Run `python -m tests.test_fingerprint` and the alert/cache tests (`pytest tests/test_alerts.py tests/test_recommendation_cache.py`) to confirm the alert path is not regressed.
4. Submit a pull request with a clear description of what changed and why.
