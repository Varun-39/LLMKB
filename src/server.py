"""
FastAPI persistent service — loads LlamaIndex, ChromaDB, and Ollama once at startup.
Alerts hit a warm index. No cold-start penalty per request.

Endpoints:
    POST /alert          — fingerprint an alert, return a grounded recommendation
    GET  /health         — ChromaDB + Ollama status
    POST /ingest/refresh — re-index changed docs

Run:
    uvicorn src.server:app --host 127.0.0.1 --port 8000
"""

import time
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from src.alerts import SplunkAlert

# ponytail: heavy imports (LlamaIndex, ChromaDB) deferred to lifespan/endpoints
# to avoid blocking module import. Only stdlib + fastapi + pydantic at top level.

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("llmkb2")

_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load LlamaIndex settings, ChromaDB index, and BM25 index once at startup."""
    import asyncio
    from src.config import init_llama_index_settings
    from src.indexer import load_index
    from src.retrieval import get_bm25

    loop = asyncio.get_event_loop()
    # ponytail: run all blocking I/O (ChromaDB + BM25 corpus load) off the event loop
    # so uvicorn can complete startup handshake without stalling.
    await loop.run_in_executor(None, init_llama_index_settings)
    _state["index"] = await loop.run_in_executor(None, load_index)
    await loop.run_in_executor(None, get_bm25)
    logger.info("Startup complete: index + BM25 loaded")
    yield
    _state.clear()


app = FastAPI(title="LLMKB2 — AIOps Runbook Assistant", lifespan=lifespan)


# --- Models ---

class Citation(BaseModel):
    doc_id: str
    doc_type: str
    section: str
    service: str
    score: float
    score_explain: Optional[dict[str, Any]] = None


def _citations(nodes) -> list[Citation]:
    return [
        Citation(
            doc_id=n.node.metadata.get("id", "?"),
            doc_type=n.node.metadata.get("doc_type", "?"),
            section=n.node.metadata.get("section_name", "?"),
            service=n.node.metadata.get("service", "?"),
            score=round(n.score or 0, 4),
            score_explain=n.node.metadata.get("_score_explain"),
        )
        for n in nodes[:8]
    ]


# --- Endpoints ---

class FingerprintInfo(BaseModel):
    signature_id: str
    error_family: str
    root_frame: Optional[str] = None


class AlertResponse(BaseModel):
    fingerprint: FingerprintInfo
    query: str
    answer: str
    citations: list[Citation]
    latency_ms: int
    cached: bool = False
    hit_count: int = 0


@app.post("/alert", response_model=AlertResponse)
async def alert_endpoint(alert: SplunkAlert):
    """
    Demo alert intake — accepts a synthetic Splunk-webhook-shaped alert
    (see src/alerts.py and data/sample_alerts/*.json), fingerprints it,
    and returns a grounded recommendation. Stands in for the real
    Splunk/ITRS event intake API until that integration is approved.

    An identical recurring incident (same fingerprint signature_id) is served
    from src/recommendation_cache.py instead of re-running retrieval + LLM
    generation — see that module's docstring.
    """
    from src.alerts import alert_to_query
    from src.fingerprint import compute_fingerprint
    from src.query import build_query_engine
    from src import recommendation_cache

    start = time.perf_counter()

    fp = compute_fingerprint(
        raw_text=alert.result.message,
        service=alert.result.service,
        environment=alert.result.environment,
        stack_trace=alert.result.stack_trace,
    )
    fp_info = FingerprintInfo(
        signature_id=fp.signature_id,
        error_family=fp.error_family,
        root_frame=fp.root_frame,
    )

    cached = recommendation_cache.get_cached(fp.signature_id)
    if cached is not None:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.info(f"[alert] {alert.search_name} | family={fp.error_family} | CACHE HIT #{cached.hit_count} | {elapsed}ms")
        return AlertResponse(
            fingerprint=fp_info,
            query=cached.query,
            answer=cached.answer,
            citations=[Citation(**c) for c in cached.citations],
            latency_ms=elapsed,
            cached=True,
            hit_count=cached.hit_count,
        )

    query_text = alert_to_query(alert, fingerprint=fp)

    engine = build_query_engine(top_k=8, service=alert.result.service)
    response = engine.query(query_text)
    answer = str(response)
    citations = _citations(response.source_nodes)

    recommendation_cache.store(
        signature_id=fp.signature_id,
        error_family=fp.error_family,
        service=alert.result.service,
        query=query_text,
        answer=answer,
        citations=[c.model_dump() for c in citations],
    )

    elapsed = int((time.perf_counter() - start) * 1000)
    logger.info(f"[alert] {alert.search_name} | family={fp.error_family} | {elapsed}ms")

    return AlertResponse(
        fingerprint=fp_info,
        query=query_text,
        answer=answer,
        citations=citations,
        latency_ms=elapsed,
    )


@app.get("/health")
async def health():
    """Check ChromaDB + Ollama connectivity."""
    from src.config import OLLAMA_MODEL, OLLAMA_BASE_URL
    from src.indexer import get_collection_stats
    import requests as req_lib

    stats = get_collection_stats()
    try:
        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
        r = req_lib.get(url, timeout=3)
        ollama_ok = r.status_code == 200
    except Exception:
        ollama_ok = False

    return {
        "status": "ok" if ollama_ok and "total_chunks" in stats else "degraded",
        "chromadb": stats,
        "ollama": "connected" if ollama_ok else "unreachable",
        "model": OLLAMA_MODEL,
    }


@app.post("/ingest/refresh")
async def refresh():
    """Re-ingest changed documents, reload the index and BM25."""
    from src.ingest import run_ingestion
    from src.indexer import load_index
    from src.retrieval import reset_bm25, get_bm25
    from src.recommendation_cache import reset_cache

    stats = run_ingestion(force=False, local=False)
    _state["index"] = load_index()
    reset_bm25()
    get_bm25()  # rebuild
    reset_cache()  # cached answers may no longer be grounded in the updated KB
    return {"status": "refreshed", "stats": stats}
