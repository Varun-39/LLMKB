  # AI Runbook Assistant

  

  Turns monitoring alerts into evidence-backed corrective action recommendations, reducing Splunk-to-Jira analysis time from ~10-15 minutes of manual lookup to seconds. A structured operational knowledge base (incidents, runbooks, system docs) powered by a Retrieval-Augmented Generation pipeline using **LlamaIndex**, **Ollama**, **MinIO**, and **ChromaDB** — surfaced to on-call ops as a grounded **recommendation card**, not a chat answer.


  Fully local. No API keys required for the core `/alert` path. No data leaves your machine.

  ---

  ## Table of Contents

  - [Architecture](#architecture)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Usage](#usage)
  - [Knowledge Seeding (Jira / Confluence)](#knowledge-seeding-jira--confluence)
  - [API Server](#api-server)
  - [Web UI](#web-ui)
  - [Configuration](#configuration)
  - [Project Structure](#project-structure)
  - [How It Works](#how-it-works)
  - [Evaluation & Metrics](#evaluation--metrics)
  - [Model Story: Pitch Deck vs. This Build](#model-story-pitch-deck-vs-this-build)
  - [Known Gaps vs. the Pitch Deck](#known-gaps-vs-the-pitch-deck)
  - [Troubleshooting](#troubleshooting)
  - [Contributing](#contributing)

  ---

  ## Architecture

  ```
  Jira / Confluence (one-time seed) ─► wiki/Pending Review/ ─► human review/approve ─┐
                                                                                       ▼
  wiki/ (Obsidian)  →  MinIO (S3)  →  LlamaIndex Reader  →  SectionNodeParser  →  ChromaDB  →  Alert Query Engine
    edit here          storage         parse + metadata       ## split + context     vectors      fingerprint → retrieval → scoring

  Splunk alert + ITRS health context ┐
                                      ├→ fingerprint → AlertContext ┐
                                      │  outcomes.db (cohort stats) ┴→ retrieve_only() (src/query.py) → evidence nodes
          │                                    │
          ▼                                    ▼
  confidence band (src/confidence.py)  →  RecommendationCard (src/card.py, src/recommendation.py)
          │                                    │
          │                        optional LLM phrasing pass (apply_generation)
          ▼                                    ▼
    /alert response  ──────────────────►  ops UI (ui/)  ──►  POST /cards/{id}/feedback
                                                                      │
                                                      feedback.db (audit)  +  ticket_client (stub)
                                                                      │
                                                           GET /metrics (feedback.db rollup)
  ```

  ### Pipeline Components

  | Layer | Technology | Role |
  |-------|-----------|------|
  | Knowledge seeding | `scripts/import_atlassian_seed.py` | One-time Jira/Confluence import into `wiki/Pending Review/`, excluded from ingestion until a human reviews and moves it into a real category folder |
  | Document source | MinIO / local `wiki/` | S3-compatible object store for Markdown files |
  | Loading | Custom `BaseReader` subclasses | Parse YAML frontmatter, normalize metadata (incl. `error_family`, `resolution_runbook`, `resolution_outcome`); excludes `Templates/` and `Pending Review/` |
  | Chunking | Custom `SectionNodeParser` | Split at `##` headers with contextual retrieval prefix |
  | Embedding | Ollama `nomic-embed-text` (768d) | Local embeddings via LlamaIndex `OllamaEmbedding` |
  | Vector store | ChromaDB (persistent) | Cosine similarity search with metadata filters |
  | Keyword search | In-memory BM25 | Full-corpus exact-term matching for IDs and rare tokens |
  | Hybrid fusion | Reciprocal Rank Fusion (RRF) | Merges dense + BM25 candidate pools (recall stage only — does not affect final ranking) |
  | Reranking | Cross-encoder (disabled by default) | `ms-marco-MiniLM-L-2-v2`; narrows the candidate pool before scoring — toggle via `config/scoring.yaml`'s `reranker.enabled` |
  | Multi-signal scoring | YAML-configured scorer | `exact_error_match`, `component_match`, `source_quality`, `past_fix_success` (equal-weighted core 4) + `section_relevance` (auxiliary) |
  | Cohort confidence | `src/confidence.py` + `src/outcomes.py` | Bands a recommendation's confidence (`high`/`medium`/`low`/`none`) from historical resolution outcomes, never from retrieval scores |
  | Card assembly | `src/recommendation.py` + `src/card.py` | Composes a grounded `RecommendationCard` — never recommends an action without evidence and a confidence band above `none` |
  | Generation (optional) | Ollama `llama3.1` | Rewrite-only phrasing pass over the already-grounded action text — cannot add facts, steps, or risks |
  | Orchestration | FastAPI + LlamaIndex | Chains fingerprint → retrieval → confidence → card → (optional) generation |
  | Delta tracking | SQLite manifest | SHA-256 hashing to skip unchanged files |
  | Error fingerprinting | `src/fingerprint.py` | Deterministic alert → KB match key (no LLM); hashes top 3 in-app stack frames, not just the first |
  | Recommendation cache | `src/recommendation_cache.py` | SQLite, keyed by fingerprint signature — repeat incidents skip retrieval + generation entirely |
  | Ops feedback | `src/feedback.py` | Append-only audit trail of accept/edit/reject/escalate/kb_gap decisions on cards |
  | Ticket routing | `src/ticket_client.py` | Stub only (`mode: noop`) — logs and mock-returns, no live Jira call; `kb_gap` decisions also queue into `review/kb_gap_proposals.json` |
  | Observability rollup | `src/metrics.py` | `feedback.db` rollup: acceptance rate, false-match rate, escalate rate, KB-gap count — `time_saved`/`precision` reported as explicit "not measured" notes, never fabricated |
  | Ops UI | `ui/` (React + Vite + Tailwind) | Fires sample alerts at `/alert`, renders the card (including ITRS context), submits feedback |

  ---

  ## Prerequisites

  - **Python 3.11+**
  - **Ollama** installed and running ([install guide](https://ollama.com))
  - **MinIO** binary (Windows: `C:\minio\minio.exe`, Linux/macOS: see [MinIO docs](https://min.io/docs/minio/linux/index.html))
  - **Node.js 18+** (only needed to run the [web UI](#web-ui))

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

  ### Build the outcomes cohort store

  Required before `past_fix_success` scoring or confidence bands are meaningful — rebuild after any `wiki/Incidents/` enrichment change:

  ```bash
  python -m src.outcomes
  ```

  This is a full rebuild (DELETE + re-INSERT) derived entirely from `wiki/Incidents/` frontmatter — `outcomes.db` is disposable and never hand-edited.

  There is no free-text query CLI or API — the only way to get a recommendation is `POST /alert` (see below). `src/query.py` is a library module consumed by the card assembly pipeline, not a standalone tool.

  ---

  ## Knowledge Seeding (Jira / Confluence)

  The deck's Markdown Knowledge Layer names a "Jira one-time seed" pipeline step — a real one-time import, not a repeating sync — that's distinct from `scripts/sync_to_minio.py` (which pushes an already-Markdown `wiki/` to storage, every time).

  ```bash
  # Default: reads data/sample_atlassian_export/*.json (synthetic export fixtures — no credentials needed)
  python scripts/import_atlassian_seed.py

  # Preview without writing anything
  python scripts/import_atlassian_seed.py --dry-run

  # Real Jira/Confluence Cloud REST APIs (needs ATLASSIAN_EMAIL/ATLASSIAN_API_TOKEN/
  # JIRA_BASE_URL/CONFLUENCE_BASE_URL etc. in .env — see .env.example)
  python scripts/import_atlassian_seed.py --source live
  ```

  Output lands in `wiki/Pending Review/`, which `src/loader.py` excludes from ingestion the same way it excludes `Templates/` — imported content is **never auto-approved**. A human reads each file, adds `error_family`/`resolution_runbook`/`resolution_outcome` if it's an incident, and moves it into a real category folder (`Incidents/`, `Runbooks/`, `System/`, ...) before `python -m src.ingest` can ever see it. This mirrors the deck's "Git Review Workflow" component (review, approval, rollback, ownership) — the review happens in git, on files a human moved there on purpose.

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
  | `POST` | `/alert` | Demo alert intake (synthetic Splunk-webhook JSON, see `data/sample_alerts/`) → fingerprint → grounded `RecommendationCard`, cached by signature. Optional `?generation=true/false` query param overrides `config/card.yaml`'s default. |
  | `POST` | `/cards/{correlation_id}/feedback` | Ops decision on a card (`accept`/`edit`/`reject`/`escalate`/`kb_gap`) → recorded append-only in `feedback.db`, routed to the ticket client (comment on `accept`/`edit`/`reject`/`escalate`, KB-gap proposal queued on `kb_gap`) |
  | `GET` | `/health` | ChromaDB + Ollama connectivity status |
  | `GET` | `/metrics` | `feedback.db` rollup — acceptance rate, false-match rate, escalate rate, KB-gap count, per-`error_family` breakdown. `time_saved` and `precision` come back as explicit "not measured" strings (see [Evaluation & Metrics](#evaluation--metrics)) |
  | `POST` | `/ingest/refresh` | Re-index changed documents, reload, and reset the recommendation cache (cached cards may no longer be grounded in the updated KB) |

  ### Alert intake (demo)

  No live Splunk/ITRS integration yet — `/alert` takes a JSON payload shaped like a Splunk webhook alert action, plus an optional `itrs` block for ITRS Geneos-style health context (process/host status, dependency latency — see [`src/alerts.py`](src/alerts.py)'s `ITRSContext`). Sample payloads live in [`data/sample_alerts/`](data/sample_alerts); `alert-connection-pool-exhausted.json` includes an `itrs` block matching the deck's own worked card example (DB latency + listener instability):

  ```bash
  curl -X POST http://localhost:8000/alert \
    -H "Content-Type: application/json" \
    -d @data/sample_alerts/alert-connection-pool-exhausted.json
  ```

  The response is a `RecommendationCard`: detected issue (including the ITRS context clause, when present), recommended action (or `null` if evidence/confidence isn't strong enough — a card never guesses), evidence with plain-language "why matched" text, a confidence band, risk/do-not-do/escalate-if guidance, and an empty `ops_decision` slot for the UI to fill in via the feedback endpoint.

  ITRS itself is schema-only here, same simplification as Splunk: there is no live ITRS Geneos API/webhook client, only the JSON shape a real one would eventually populate (see the `ponytail:` note on `ITRSContext`).

  ---

  ## Web UI

  An ops-facing React app for triggering sample alerts and reviewing/deciding on the resulting card.

  ```bash
  cd ui
  npm install
  npm run dev
  ```

  Vite proxies `/alert`, `/cards`, `/health`, and `/ingest` to `http://127.0.0.1:8000`, so start the FastAPI server first. Trigger a sample alert from the strip at the top, review the rendered card (detected issue, confidence, evidence, risk), and record a decision through the panel at the bottom — this posts to `/cards/{id}/feedback`.

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

  # SQLite recommendation cache (keyed by alert fingerprint signature_id)
  RECOMMENDATION_CACHE_DB=./recommendations.db

  # SQLite outcomes store (cohort data for confidence — derived from wiki/Incidents/, rebuildable)
  OUTCOMES_DB=./outcomes.db

  # SQLite feedback store (ops decisions — append-only audit trail, NOT derived)
  FEEDBACK_DB=./feedback.db

  # Wiki source directory
  WIKI_SOURCE_DIR=./wiki

  # Atlassian one-time KB seed importer — optional, only for
  # `scripts/import_atlassian_seed.py --source live` (default --source is
  # "export" and needs none of this). See .env.example for the full list
  # (ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN, JIRA_BASE_URL, JIRA_JQL,
  # CONFLUENCE_BASE_URL, CONFLUENCE_SPACE_KEY).
  ```

  ### Scoring (`config/scoring.yaml`)

  All retrieval scoring parameters — no code changes needed to tune:

  - **signals** — `exact_error_match`, `component_match`, `source_quality`, `past_fix_success` (equal-weighted 0.25 each, the scoring "core 4"), plus `section_relevance` (0.10, auxiliary — matches section type to query intent, meaningful mainly for manual/CLI queries). Each signal has an `enabled` flag; disabling one contributes 0, not a neutral value. RRF is deliberately excluded from this list — it drives the recall/candidate-pool stage in `src/retrieval.py`, not final ranking.
  - **penalties** — score deductions for low-value sections (`links`, `revision-history`)
  - **thresholds** — ID-routing regex, candidate multiplier, `min_candidate_count`, RRF constant
  - **candidate_pool.final_top_k** — how many evidence items reach the card (separate from the recall-stage pool size above)
  - **retrieval_filters** — `service_filter_mode: strict` (dense retrieval excludes non-matching services) vs. `error_family_filter_mode: soft` (not filtered — scoring rewards matches instead, since `error_family` enrichment coverage is incomplete)
  - **explanations** — templates for the plain-language "why this matched" text attached to each evidence item
  - **intent_keywords** — classify query as "action" (fix/resolve/how) vs "info" (what/why/timeline); bypassed on the alert path in favor of structured `AlertContext` fields
  - **source_quality_tiers** — authority tier per `doc_type`: `runbook` (1.0) > `incident` (0.75) > `system` (0.5) > `vendor-note`/`governance`/`template`/unknown (0.2)
  - **doc_coherence** — boost for documents with multiple chunks in the candidate pool
  - **reranker** — toggle cross-encoder candidate-pool narrowing and set model/top-n

  ### Confidence (`config/confidence.yaml`)

  Bands a recommendation's confidence from historical resolution outcomes in `outcomes.db` — completely separate from retrieval/ranking scores:

  - **bands** — score thresholds for `high` (≥0.85), `medium` (≥0.60), `low` (≥0.35); below that, `none`
  - **min_cohort_size** — hard floor (default 3); too few prior incidents forces `none` regardless of ratio
  - **count_as_success** / **count_as_attempt** / **exclude_outcomes** — which `resolution_outcome` values count toward the ratio; `unknown` is excluded from both numerator and denominator, never miscounted either way
  - **require_same_runbook** — if true, "success" means this specific runbook worked, not just that the error family was generally survivable
  - **treat_low_as_no_action** — `true` (reconciled against the deck — see below). A `low`-scoring cohort is converted to band `none` before it ever reaches a card, so `recommended_action` comes back `null` exactly as for `none`. The raw score/ratio is still computed and returned on `Confidence` for audit/tuning; this only changes which band a client sees.

  This same file's `count_as_success`/`count_as_attempt`/`exclude_outcomes` are shared with `src/query.py`'s `past_fix_success` scoring signal, so a "cohort" means the same thing in both places.

  **Reconciled against the deck:** slide 10's confidence story is 3-state — "High = recommend; medium = caveated recommendation; low = no strong knowledge match found" — with no separate caveated-but-shown `low` tier. `src/confidence.py` computes 4 internal bands (`high`/`medium`/`low`/`none`) because the `low` boundary is a useful tuning knob, but `treat_low_as_no_action: true` collapses `low` into `none` before any client ever sees it, so the code's externally-visible behavior now matches the deck's 3-state story exactly. Flip that flag back to `false` only if the product decides to show a caveated low-confidence action again.

  ### Card (`config/card.yaml`)

  Controls what a `RecommendationCard` shows and whether generation runs:

  - **fields** — `show_do_not_do`, `show_escalate_if`, `show_risk`, `max_evidence_items`
  - **generation.enabled** — master switch for the optional LLM phrasing pass; when `false`, the card still assembles fully from retrieval + confidence, just without rephrasing
  - **generation.model_version_tag** — recorded on the card when generation runs

  ### Feedback (`config/feedback.yaml`)

  - **valid_decisions** — `accept` / `edit` / `reject` / `escalate` / `kb_gap`
  - **require_comment_for** — decisions that must include a comment (`reject`, `escalate`, `kb_gap`)
  - **edited_action_required_for** — decisions that must include the edited text (`edit`)

  ### Ticketing (`config/jira.yaml`)

  - **mode** — `noop` is the only implemented value. No live Jira integration exists; `NoopTicketClient` logs and returns a mock `MOCK-xxxxxx` issue key. `create_kb_gap()` additionally appends to `review/kb_gap_proposals.json`, a local human-review queue (propose-only — nothing reads or auto-applies `status` yet).

  ### Fingerprinting (`config/fingerprint.yaml`)

  Rules for deterministic error fingerprinting — no code changes needed:

  - **volatile_patterns** — regex substitutions to strip timestamps, UUIDs, IPs, instance numbers before hashing
  - **framework_frame_prefixes** — JVM/framework package prefixes to skip during stack trace root-frame extraction
  - **error_families** — 23 pattern-to-family mappings keyed to runbook slugs (`connection-pool-exhausted`, `oom`, `disk-full`, etc.)

  ---

  ## Project Structure

  ```
  LLMKB/
  ├── wiki/                        # Markdown knowledge base (Obsidian vault) — approved content only
  │   ├── Incidents/               # 100 incident reports (INC-001 – INC-100)
  │   ├── Runbooks/                # 42 operational runbooks (RB-001 – RB-042)
  │   ├── System/                  # 5 service architecture docs (SYS-001 – SYS-005)
  │   ├── Governance/               # Escalation rules, guardrails
  │   ├── Templates/               # Document templates (excluded from indexing)
  │   ├── Vendor notes/             # Third-party tooling notes
  │   └── Pending Review/          # scripts/import_atlassian_seed.py output — excluded from indexing until a human reviews and moves it
  ├── src/
  │   ├── config.py                # Env config + LlamaIndex Settings init
  │   ├── loader.py                # MinIO/local readers (LlamaIndex BaseReader); excludes Templates/ and Pending Review/
  │   ├── chunker.py               # SectionNodeParser: ## boundaries + contextual prefix
  │   ├── indexer.py               # ChromaDB VectorStoreIndex management
  │   ├── manifest.py              # SQLite delta tracking (SHA-256 per file)
  │   ├── ingest.py                # Ingestion pipeline (load → parse → embed → store)
  │   ├── retrieval.py             # BM25, RRF hybrid fusion (recall stage)
  │   ├── query.py                 # Retrieval + multi-signal scoring library, consumed by src/recommendation.py
  │   ├── fingerprint.py           # Deterministic alert → signature_id (no LLM)
  │   ├── alerts.py                # Splunk-webhook-shaped alert payload + ITRSContext + AlertContext + query builder
  │   ├── outcomes.py              # Builds/queries outcomes.db cohort store from wiki/Incidents/ frontmatter
  │   ├── confidence.py            # Cohort-ratio confidence banding (high/medium/low/none; low folded into none)
  │   ├── card.py                  # RecommendationCard pydantic schema + grounding invariants
  │   ├── recommendation.py        # Assembles a card from retrieval + confidence; optional LLM phrasing pass
  │   ├── feedback.py               # Ops decision validation + append-only feedback.db writes
  │   ├── ticket_client.py          # Stub ticket routing (noop mode) + kb_gap review queue
  │   ├── metrics.py                # feedback.db rollup: acceptance/false-match/escalate rate, KB-gap count
  │   ├── server.py                 # FastAPI server: /alert, /cards/{id}/feedback, /health, /metrics, /ingest/refresh
  │   └── recommendation_cache.py  # SQLite cache, keyed by fingerprint signature_id
  ├── config/
  │   ├── scoring.yaml              # Retrieval scoring signals and tuning
  │   ├── confidence.yaml           # Cohort confidence bands and thresholds (low folded into none — deck reconciliation)
  │   ├── card.yaml                 # Card field visibility + generation toggle
  │   ├── feedback.yaml             # Valid ops decisions + comment/edit requirements
  │   ├── jira.yaml                 # Ticket client mode (noop only)
  │   ├── fingerprint.yaml          # Fingerprint normalization + error family rules
  │   └── prompts/
  │       └── card_prompt.yaml      # Rewrite-only LLM prompt for the optional phrasing pass
  ├── scripts/
  │   ├── import_atlassian_seed.py # One-time Jira/Confluence seed importer -> wiki/Pending Review/
  │   ├── sync_to_minio.py         # One-way wiki/ → MinIO sync (repeating, unlike the importer above)
  │   └── start_minio.bat          # Start MinIO server (Windows)
  ├── data/
  │   ├── sample_alerts/           # Sample Splunk-webhook-shaped alert JSON payloads (one includes an itrs block)
  │   └── sample_atlassian_export/ # Synthetic Jira/Confluence export fixtures for the seed importer's default mode
  ├── ui/                           # React + Vite + Tailwind ops UI (trigger alerts, review cards, submit feedback)
  ├── review/
  │   └── kb_gap_proposals.json    # Human review queue for kb_gap feedback decisions (local, gitignored)
  ├── tests/
  │   ├── test_fingerprint.py      # Fingerprint self-check (plain asserts)
  │   ├── test_alerts.py           # Alert payload / query-builder tests, incl. ITRS clause reaching the query
  │   ├── test_confidence.py       # Low-band -> none demotion (deck reconciliation) self-check
  │   ├── test_card.py             # RecommendationCard recommended_runbook field + R2 grounding invariants
  │   ├── test_recommendation_cache.py  # Recommendation cache tests
  │   ├── test_alert_cache_correlation.py  # Cache-hit cards get a fresh correlation_id, same grounded content
  │   ├── test_metrics.py          # feedback.db rollup self-check
  │   ├── test_atlassian_import.py # Seed importer conversion + Pending Review/ exclusion self-check
  │   ├── evaluate.py              # Recall@3/MRR over free-text queries (tests/validation_queries.json)
  │   ├── evaluate_alert_path.py   # Recall@3/MRR through the real alert path + confidence band per case
  │   ├── evaluate_replay.py       # 100-incident replay/calibration harness (synthetic alerts from incident text)
  │   └── evaluate_v2.py            # LlamaIndex eval suite (Hit Rate/MRR/NDCG/Precision/Recall, optional generation eval)
  ├── chroma_db/                   # ChromaDB persistence (gitignored)
  ├── manifest.db                  # SQLite delta manifest (gitignored)
  ├── recommendations.db           # SQLite recommendation cache (gitignored)
  ├── outcomes.db                  # SQLite outcomes cohort store (gitignored, rebuild via python -m src.outcomes)
  ├── feedback.db                  # SQLite feedback audit trail (gitignored, local demo data)
  ├── requirements.txt
  ├── .env.example
  └── .gitignore
  ```

  ---

  ## How It Works

  ### Loading (`src/loader.py`)

  `MinIOMarkdownReader` and `LocalMarkdownReader` both parse YAML frontmatter from each `.md` file and normalize metadata into consistent fields (`doc_type`, `id`, `service`, `severity`, `tags`, `object_key`, and — for incidents — `error_family`, `resolution_runbook`, `resolution_outcome`). `Templates/`, `Pending Review/`, and `.obsidian` files are excluded automatically — `Pending Review/` is where [`scripts/import_atlassian_seed.py`](#knowledge-seeding-jira--confluence) lands unreviewed Jira/Confluence content, and it stays invisible to retrieval until a human moves it into a real category folder.

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
  3. **Hybrid fusion** — dense (cosine) candidates and BM25 candidates are unioned and merged via **Reciprocal Rank Fusion (RRF)**. BM25-only hits enter the pool even if they ranked outside the dense top-k. RRF only sizes and orders the *recall* pool — it is not itself a scoring signal.

  ### Scoring (`src/query.py`)

  After the candidate pool is built, an optional **cross-encoder reranker** narrows it further (CPU-friendly, disabled by default). Then `MultiSignalScorer` combines the five signals defined in `config/scoring.yaml`:

  | Signal | What it measures |
  |--------|-----------------|
  | Exact error match | Structured `error_family` match against the alert, falling back to IDF-weighted text overlap on manual/CLI queries |
  | Component match | Alert's structured service/component against the candidate's `service` metadata |
  | Source quality | Authority tier: runbook > incident > system > vendor-note/governance/unknown |
  | Past fix success | `outcomes.db` cohort ratio for the candidate's associated runbook; neutral (0.5) — never penalized or boosted — when the cohort is too small to judge |
  | Section relevance (auxiliary) | Section type matches query intent (action vs. info) |

  On the alert path, `is_action_query`/`is_info_query`/`query_service` read the structured `AlertContext` (built in `src/alerts.py` from the alert + its fingerprint + its optional ITRS context) instead of sniffing keywords out of the rendered query sentence — the rendered sentence's boilerplate wording ("...is reporting: ...") can spuriously match unrelated keywords. A **document coherence boost** rewards documents with multiple chunks in the candidate pool. `_score_explain` records every signal's raw contribution per candidate for audit, including the RRF score that no longer drives ranking. All signals and weights are in `config/scoring.yaml` — no code changes needed to tune.

  ### ITRS Context (`src/alerts.py`)

  An alert's `itrs` block (`ITRSContext`) carries an ITRS Geneos-style health snapshot alongside the Splunk symptom — process/host status, a named dependency and its status, and latency — matching the deck's "Context-aware: combine ... host, component, environment and ITRS health state" design principle. When it reports something noteworthy (not fully healthy), `ITRSContext.summary()` produces a short clause ("ITRS shows database degraded (latency 850ms). DB listener instability observed.") that's appended to the retrieval query text and surfaced on the card's `detected_issue.itrs_context`. This is schema-only, the same simplification as the rest of the alert path (see [Model Story](#model-story-pitch-deck-vs-this-build)) — there is no live ITRS Geneos API/webhook client, only the JSON shape one would eventually populate.

  ### Cohort Confidence (`src/confidence.py`, `src/outcomes.py`)

  `outcomes.db` is a SQLite table derived entirely from `wiki/Incidents/` frontmatter (`error_family`, `resolution_runbook`, `resolution_outcome`) — rebuilt with `python -m src.outcomes`, never hand-edited. `compute_confidence(error_family, resolution_runbook)` queries the cohort's success ratio and buckets it into a band (`high`/`medium`/`low`/`none`), enforcing a minimum cohort size (default 3) so a 2-for-2 cohort can't read as high confidence. `low` is then folded into `none` (`config/confidence.yaml`'s `treat_low_as_no_action: true`) so the card's externally-visible bands match the deck's 3-state story exactly — see [Confidence](#confidence-configconfidenceyaml) above. This computation never touches embedding/RRF/reranker scores — it answers "has this fix actually worked before," a different question from "is this document relevant."

  ### Recommendation Cards (`src/card.py`, `src/recommendation.py`)

  `build_recommendation_card()` retrieves evidence via `src.query.retrieve_only()`, finds the best-supported runbook among the ranked nodes, computes its confidence band, and assembles a `RecommendationCard` — entirely without an LLM call. Two invariants are enforced at construction time (not just by convention): a card can't carry a `recommended_action` without non-empty `evidence`, and it can't carry a `recommended_action` when `confidence.band == "none"`. If evidence or confidence isn't strong enough, `recommended_action` is `null` — the card says "no strong knowledge match" rather than guessing.

  An optional, separate `apply_generation()` step can rephrase the (already-grounded) action text through Ollama, using `config/prompts/card_prompt.yaml` — a rewrite-only prompt that's explicitly forbidden from adding or removing any command, step, fact, risk, or escalation criterion, and must emit `REFUSE: ...` rather than comply if it can't. Controlled by `config/card.yaml`'s `generation.enabled`.

  ### Ops Feedback (`src/feedback.py`)

  Ops record a decision on a card — `accept`, `edit`, `reject`, `escalate`, or `kb_gap` — via `POST /cards/{correlation_id}/feedback`. Each decision is validated (comments required for `reject`/`escalate`/`kb_gap`, edited text required for `edit`) and inserted as a new row into `feedback.db`, **never updated in place** — a re-decided card produces a new audit row, so history is preserved. Unlike the other SQLite stores, `feedback.db` is a genuine system of record, not a derived/rebuildable cache.

  ### Ticket Routing (`src/ticket_client.py`)

  Stub only — `config/jira.yaml`'s `mode: noop` is the only implemented mode, and there is no Jira SDK dependency or API credential anywhere in this repo. `NoopTicketClient` logs the call and returns a mock issue key; `kb_gap` decisions additionally append a proposal to `review/kb_gap_proposals.json` for a human to review later. Nothing auto-applies from that queue.

  ### Observability Rollup (`src/metrics.py`)

  `GET /metrics` (or `python -m src.metrics`) rolls `feedback.db` up into acceptance rate (`accept`+`edit` / total — the recommendation was used, as-is or amended), false-match rate (`reject` / total), escalate rate, KB-gap count, and a per-`error_family` breakdown — the deck's slide-10 "Observability" guardrail. `time_saved` and `precision` come back as explicit strings saying they're **not measured**, rather than a fabricated number: `feedback.db` records `decided_at` but never the alert's original intake time, so time-to-decision (and therefore time saved against the deck's own 10-15 min manual baseline) isn't derivable from current data without persisting alert receipt time somewhere; precision needs an independent correctness label per recommendation, which nothing here captures (accept/edit vs. reject is an ops *preference* signal, not a verified-correct one).

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

  ## Evaluation & Metrics

  Retrieval-quality evaluation (offline, ground-truth-based):

  | Command | What it measures |
  |---------|-------------------|
  | `python -m tests.evaluate` | Recall@3 / MRR over free-text queries (`tests/validation_queries.json`) |
  | `python -m tests.evaluate_alert_path` | Recall@3 / MRR through the real alert path (`tests/alert_validation_cases.json`), plus achieved confidence band per case |
  | `python -m tests.evaluate_replay` | 100-incident replay: builds a synthetic alert from each incident's own Summary/Symptoms text (never Resolution, to avoid leaking the answer) and checks whether the recommended runbook matches ground truth; reports the count of `error_family: unknown` incidents excluded from scoring |
  | `python -m tests.evaluate_v2` | LlamaIndex eval suite (Hit Rate/MRR/NDCG/Precision/Recall); `--with-generation` adds Faithfulness/Relevancy checks, `--generate-synthetic N` generates synthetic QA pairs |

  Live ops-usage rollup (online, from real feedback):

  | Command | What it measures |
  |---------|-------------------|
  | `python -m src.metrics` / `GET /metrics` | `feedback.db` rollup — acceptance rate, false-match rate, escalate rate, KB-gap count, per-`error_family` breakdown. `time_saved` and `precision` are explicit "not measured" notes, not numbers — see [Observability Rollup](#observability-rollup-srcmetricspy) above for why. |

  ---

  ## Model Story: Pitch Deck vs. This Build

  The deck's "Model Options for Recommendation Generation" slide (11) pitches a pluggable catalog for the phrasing pass: open-source (Llama 3.1/3.3, Mistral/Mixtral, Phi, Qwen) and AWS Bedrock (Claude 3.5/3.7 Sonnet, Amazon Nova Pro/Lite, Mistral via Bedrock, Meta Llama via Bedrock), selected later on data residency, latency, cost, evidence adherence, and security approval.

  **This build runs local Ollama (`llama3.1`) only, hardcoded.** `src/config.py`'s `init_llama_index_settings()` constructs a single `Ollama(...)` LLM and a single `OllamaEmbedding(...)` — there is no provider abstraction, no Bedrock client, no model-selection config anywhere in this repo. That's a deliberate demo simplification (fully-local, no API keys, no cloud spend, no security-approval lead time while retrieval/scoring/confidence/card assembly are being proven out — exactly the deck's own "start with decision support, then mature" phasing), stated here explicitly rather than left for someone to discover by grepping for `boto3` and finding nothing. Swapping in a pluggable provider catalog is real, scoped future work: it touches exactly `init_llama_index_settings()` and `apply_generation()`'s `Settings.llm.complete()` call — retrieval, scoring, confidence, and card assembly are all already LLM-free (see [Recommendation Cards](#recommendation-cards-srccardpy-srcrecommendationpy)) and need no change.

  ---

  ## Known Gaps vs. the Pitch Deck

  The deck's slide 10 ("Enterprise guardrails for trust, safety and auditability") claims a set of governance controls for Phase 1. This build implements some of them and not others — flagged here explicitly rather than left to look done by omission:

  | Deck claim | Status here |
  |---|---|
  | No execution / Phase 1 never runs commands | **Implemented.** `apply_generation()` only rephrases already-retrieved text; nothing in this repo executes a command. |
  | Grounding — every action references retrieved KB/incidents/runbooks | **Implemented.** `RecommendationCard`'s validators make it structurally impossible to construct a card with an action and no evidence (see [Recommendation Cards](#recommendation-cards-srccardpy-srcrecommendationpy)). |
  | Confidence bands (high/medium/low=no-match) | **Implemented**, reconciled this pass — see [Confidence](#confidence-configconfidenceyaml). |
  | Observability — acceptance rate, false matches, KB gaps, time saved | **Partially implemented.** Acceptance/false-match/escalate rate and KB-gap count are real, computed from `feedback.db` (`src/metrics.py`, `GET /metrics`). Precision and time saved are **not measured** — reported as explicit notes, not fabricated numbers (see [Observability Rollup](#observability-rollup-srcmetricspy)). |
  | Access control — respect source entitlements; log who viewed, accepted, or edited | **Partially implemented, and only half the claim.** `feedback.db` logs who *decided* (`actor` is mandatory on every accept/edit/reject/escalate/kb_gap). Nothing logs who *viewed* a card — there's no view-tracking anywhere. There is also no entitlements/authorization layer at all: `/alert`, `/cards/{id}/feedback`, `/metrics`, and `/ingest/refresh` are unauthenticated; anyone who can reach the FastAPI server can call any of them. **Deferred, not done.** |
  | Data protection — mask secrets/PII, use approved AI service endpoints only | **Not implemented. Deferred.** Alert payloads and retrieved KB text are sent to the local Ollama process as-is; there is no PII/secret-masking pass anywhere in the pipeline. "Approved AI service endpoints" is moot while the model is hardcoded to local Ollama (see [Model Story](#model-story-pitch-deck-vs-this-build)), but masking would matter the moment a cloud model provider is added, and isn't built in advance of that need. |

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
  | Every card comes back with `recommended_action: null` | Confidence bands need `outcomes.db` populated: run `python -m src.outcomes`. Also check `config/confidence.yaml`'s `min_cohort_size` isn't set higher than your corpus supports, and remember `low` is intentionally folded into `none` (see [Confidence](#confidence-configconfidenceyaml)) — that's not a bug. |
  | UI shows a network error on trigger | Start the FastAPI server first (`uvicorn src.server:app ...`) — Vite proxies API calls to `127.0.0.1:8000` and doesn't run a backend of its own. |
  | `import_atlassian_seed.py --source live` fails with a `KeyError` | Live mode needs `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`, `JIRA_BASE_URL`, `CONFLUENCE_BASE_URL`, and `CONFLUENCE_SPACE_KEY` set in `.env` (see [Knowledge Seeding](#knowledge-seeding-jira--confluence)). Default `--source export` needs none of this. |
  | Imported Jira/Confluence content isn't showing up in search results | Expected — it lands in `wiki/Pending Review/`, which is excluded from ingestion by design. Review the file, add `error_family`/`resolution_runbook`/`resolution_outcome` if it's an incident, move it into a real category folder, then re-run `python -m src.ingest --local`. |

  ---

  ## Contributing

  1. Fork the repository and create a feature branch.
  2. Make your changes, keeping diffs minimal and focused.
  3. Run the self-checks — `python -m tests.test_fingerprint`, `python -m tests.test_alerts`, `python -m tests.test_confidence`, `python -m tests.test_card`, `python -m tests.test_recommendation_cache`, `python -m tests.test_metrics`, `python -m tests.test_atlassian_import` (no ChromaDB/Ollama needed for any of these seven), and, with the index and Ollama running, `python -m tests.test_alert_cache_correlation` and `python -m tests.evaluate_alert_path` — to confirm the alert → card path is not regressed.
  4. Submit a pull request with a clear description of what changed and why.
