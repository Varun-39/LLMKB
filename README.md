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
- [Evaluation](#evaluation)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Architecture

```
wiki/ (Obsidian)  →  MinIO (S3)  →  LlamaIndex Reader  →  Section NodeParser  →  ChromaDB  →  Query Engine
  edit here          storage         parse + metadata       ## split to nodes      vectors      LlamaIndex + Ollama
```

### Pipeline Components

| Layer | Technology | Role |
|-------|-----------|------|
| Document source | MinIO / local `wiki/` | S3-compatible object store for Markdown files |
| Loading | Custom `BaseReader` subclasses | Parse YAML frontmatter, normalize metadata |
| Chunking | Custom `SectionNodeParser` | Split at `##` headers — never splits mid-section |
| Embedding | Ollama `nomic-embed-text` (768d) | Local embeddings via LlamaIndex `OllamaEmbedding` |
| Vector store | ChromaDB (persistent) | Cosine similarity search with metadata filters |
| Keyword search | In-memory BM25 | Full-corpus exact-term matching for IDs and rare tokens |
| Hybrid fusion | Reciprocal Rank Fusion (RRF) | Merges dense + BM25 candidate pools |
| Multi-signal scoring | YAML-configured scorer | Weighted combination of semantic, exact match, metadata, and section relevance |
| Generation | Ollama `llama3.1` | Local LLM via LlamaIndex `Ollama` |
| Orchestration | LlamaIndex `RetrieverQueryEngine` | Chains retrieval → synthesis with custom SRE prompt |
| Delta tracking | SQLite manifest | SHA-256 hashing to skip unchanged files |

---

## Prerequisites

- **Python 3.11+**
- **Ollama** installed and running ([install guide](https://ollama.com))
- **MinIO** binary (Windows: `C:\minio\minio.exe`, Linux/macOS: see [MinIO docs](https://min.io/docs/minio/linux/index.html))

---

## Installation

### 1. Clone the repository

```bash
git clone <REPOSITORY_URL>
cd LLMKB2
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
copy .env.example .env
```

Edit `.env` with your preferred settings (see [Configuration](#configuration)).

### 5. Start MinIO

```bash
scripts\start_minio.bat
```

MinIO Console: http://localhost:9001 (default credentials: `minioadmin` / `minioadmin123`)

---

## Usage

### Sync documents to MinIO

```bash
python scripts/sync_to_minio.py
```

### Build the index

```bash
# From MinIO (production path):
python -m src.ingest

# From local wiki/ (dev shortcut):
python -m src.ingest --local

# Force full re-index (bypasses delta tracking):
python -m src.ingest --local --force
```

### Query (CLI)

```bash
# Single question
python -m src.query "payment service pods are OOMKilled what should I do"

# Filter by document type
python -m src.query "how to fix connection pool exhaustion" --type runbook

# Filter by service
python -m src.query "what incidents affected auth-service" --service auth-service

# Interactive mode
python -m src.query --interactive

# Retrieve only (no LLM generation)
python -m src.query "disk full on database volume" --no-generate
```

---

## API Server

LLMKB2 includes a FastAPI server for persistent, low-latency access. The index loads once at startup — no cold-start penalty per request.

### Start the server

```bash
uvicorn src.server:app --host 127.0.0.1 --port 8000
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/query` | Retrieve + optional generation (JSON response) |
| `POST` | `/query/stream` | Streaming generation (Server-Sent Events) |
| `GET` | `/health` | ChromaDB + Ollama connectivity status |
| `POST` | `/ingest/refresh` | Re-index changed documents and reload |

### Example request

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "payment service OOMKilled", "top_k": 5}'
```

### Request body (`/query`)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `question` | string | *(required)* | The query text |
| `doc_type` | string | `null` | Filter by doc type (e.g., `runbook`, `incident`) |
| `service` | string | `null` | Filter by service name |
| `severity` | string | `null` | Filter by severity |
| `top_k` | int | `8` | Number of results to retrieve |
| `no_generate` | bool | `false` | Skip LLM generation, return retrieved chunks only |

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

### Scoring configuration

Retrieval scoring weights, intent keywords, and penalties are configured in `config/scoring.yaml`. Edit this file to tune ranking behavior without code changes.

Key settings:
- **weights** — relative importance of semantic, exact match, metadata match, and section relevance signals
- **penalties** — low-value section penalties (e.g., "links", "revision-history")
- **thresholds** — ID-routing regex, candidate multiplier, RRF constant
- **intent_keywords** — words that classify a query as "action" vs "info" intent

---

## Evaluation

A retrieval evaluation harness measures quality before and after scoring changes:

```bash
# Run with default settings
python -m tests.evaluate

# Custom top-k
python -m tests.evaluate --top-k 5

# Show per-query results
python -m tests.evaluate --verbose
```

Metrics reported:
- **Recall@3** — was an expected document in the top 3 results?
- **MRR** — mean reciprocal rank of the first expected document

Test cases live in `tests/validation_queries.json`.

---

## Project Structure

```
LLMKB2/
├── wiki/                       # Markdown knowledge base (Obsidian vault)
│   ├── Incidents/              # Incident reports
│   ├── Runbooks/               # Operational runbooks
│   ├── System/                 # Service documentation
│   ├── Governance/             # Escalation rules, guardrails
│   ├── Templates/              # Document templates (excluded from indexing)
│   └── Vendor notes/           # Third-party tooling notes
├── src/
│   ├── config.py               # Configuration + LlamaIndex Settings init
│   ├── loader.py               # MinIO/local readers (LlamaIndex BaseReader)
│   ├── chunker.py              # Section-level NodeParser (## boundaries)
│   ├── indexer.py              # ChromaDB VectorStoreIndex management
│   ├── manifest.py             # SQLite delta tracking
│   ├── ingest.py               # Ingestion pipeline (load → parse → embed → store)
│   ├── retrieval.py            # BM25, hybrid fusion, multi-signal scoring
│   ├── query.py                # Query engine (retrieve → rerank → generate)
│   └── server.py               # FastAPI server (persistent warm index)
├── config/
│   └── scoring.yaml            # Retrieval scoring weights and tuning
├── scripts/
│   ├── sync_to_minio.py        # One-way wiki/ → MinIO sync
│   └── start_minio.bat         # Start MinIO server (Windows)
├── tests/
│   ├── evaluate.py             # Retrieval evaluation harness (Recall@3, MRR)
│   └── validation_queries.json # Ground-truth query/expected-doc pairs
├── chroma_db/                  # ChromaDB persistence (gitignored)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## How It Works

### Loading (`src/loader.py`)

- `MinIOMarkdownReader` loads from MinIO bucket via S3 API
- `LocalMarkdownReader` loads from local `wiki/` directory
- Both parse YAML frontmatter and normalize metadata (service, severity, doc_type, tags)
- Returns LlamaIndex `Document` objects with rich metadata

### Chunking (`src/chunker.py`)

- Custom `SectionNodeParser` splits at `##` header boundaries
- Each section becomes one `TextNode` — never splits within a section
- Preserves full "Resolution" blocks with all Mitigate/Fix/Verify steps together
- Nodes inherit parent metadata + get `section_name` and `section_index`

### Retrieval (`src/retrieval.py`)

- **ID routing** — queries matching a document ID pattern (e.g., `INC-003`) bypass vector search and do a direct metadata lookup
- **BM25 keyword search** — in-memory inverted index over all nodes in ChromaDB; catches exact-term matches that dense retrieval misses
- **Hybrid fusion** — union of dense (cosine) candidates and BM25 candidates, fused via Reciprocal Rank Fusion
- **Multi-signal scorer** — weighted combination of semantic similarity, exact match, metadata match, and section relevance

### Indexing (`src/indexer.py`)

- Wraps ChromaDB in LlamaIndex's `ChromaVectorStore`
- `build_index_from_documents()` — full index construction
- `insert_nodes()` — incremental delta updates
- `load_index()` — load existing index at query time (no re-embedding)

### Querying (`src/query.py`)

- `VectorIndexRetriever` with `MetadataFilters` for service/severity/doc_type
- Custom SRE prompt template enforces grounded answers with citations
- `RetrieverQueryEngine` chains retrieval → synthesis

### Delta Re-indexing (`src/manifest.py`)

- SQLite stores SHA-256 hash per file
- Only changed/new files get re-embedded on subsequent runs
- `--force` flag bypasses manifest for full rebuild

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Cannot connect to Ollama" | Run `ollama serve` |
| "Model not found" | `ollama pull llama3.1` and `ollama pull nomic-embed-text` |
| "No relevant chunks found" | `python -m src.ingest --local --force` |
| MinIO connection refused | `scripts\start_minio.bat` |
| Slow first ingest | Normal — local embedding takes a few minutes. Delta runs are fast. |
| API server won't start | Ensure index exists (`python -m src.ingest --local` first) |

---

## Contributing

Contributions are welcome. To get started:

1. Fork the repository and create a feature branch.
2. Make your changes, keeping diffs minimal and focused.
3. Run the evaluation harness (`python -m tests.evaluate`) to ensure retrieval quality is maintained.
4. Submit a pull request with a clear description of what changed and why.

Please follow the existing code style and patterns. If adding a new retrieval signal or scoring change, include before/after evaluation results in the PR description.

---

