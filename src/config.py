"""
Central configuration loaded from environment variables.
Uses Ollama for LLM/embeddings, MinIO for document storage, ChromaDB for vectors.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

# --- Ollama ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# --- MinIO ---
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "llmkb")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# --- ChromaDB ---
CHROMA_PERSIST_DIR = str(_project_root / os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"))
CHROMA_COLLECTION = "llmkb_docs"

# --- SQLite Manifest ---
MANIFEST_DB = str(_project_root / os.getenv("MANIFEST_DB", "./manifest.db"))

# --- SQLite Recommendation Cache (keyed by fingerprint signature_id) ---
RECOMMENDATION_CACHE_DB = str(_project_root / os.getenv("RECOMMENDATION_CACHE_DB", "./recommendations.db"))

# --- SQLite Outcomes store (cohort data for past_fix_success / confidence) ---
# Derived from wiki/Incidents/ frontmatter — rebuildable at any time (R4).
# Never hand-edit; re-run src.outcomes.build_outcomes_db() after any enrichment change.
OUTCOMES_DB = str(_project_root / os.getenv("OUTCOMES_DB", "./outcomes.db"))

# --- SQLite Feedback store (ops decisions on recommendation cards) ---
# Append-only audit trail (R8) — NOT derived, this is a genuine system-of-record
# (the decision plane, R6) and must never be wiped/rebuilt like the derived stores above.
FEEDBACK_DB = str(_project_root / os.getenv("FEEDBACK_DB", "./feedback.db"))

# --- Wiki Source (local editing surface, synced to MinIO) ---
WIKI_SOURCE_DIR = str(_project_root / os.getenv("WIKI_SOURCE_DIR", "./wiki"))

# --- Doc type mapping (folder prefix -> doc_type) ---
DOC_TYPE_MAP = {
    "Incidents": "incident",
    "Runbooks": "runbook",
    "System": "system",
    "Governance": "governance",
    "Templates": "template",
    "Vendor notes": "vendor-note",
}


def init_llama_index_settings():
    """
    Configure LlamaIndex global Settings with Ollama LLM and embeddings.
    Call once at startup before any LlamaIndex operations.
    """
    from llama_index.core import Settings
    from llama_index.llms.ollama import Ollama
    from llama_index.embeddings.ollama import OllamaEmbedding

    Settings.llm = Ollama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        request_timeout=120.0,
        temperature=0.1,
        # ponytail: default context_window=-1 makes LlamaIndex request llama3.1's full
        # 131072-token context from Ollama, which doesn't fit an 8B model's KV cache in
        # 8GB VRAM and forces ~74% of inference onto CPU (10x+ slower). Our prompts
        # (card phrasing prompt + top_k chunks) are a few thousand tokens at most — 8192 covers
        # that with headroom while keeping the whole KV cache on GPU. Raise if chunk_size
        # or top_k grow enough to truncate context.
        context_window=8192,
    )
    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )
    # We use our own section-based parser, disable LlamaIndex's default chunking
    Settings.chunk_size = 4096
    Settings.chunk_overlap = 0
