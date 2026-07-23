"""
FastAPI persistent service — loads LlamaIndex, ChromaDB, and Ollama once at startup.
Alerts hit a warm index. No cold-start penalty per request.

Endpoints:
    POST /alert                        — fingerprint an alert, return a grounded recommendation
    POST /cards/{correlation_id}/feedback — record an ops decision on a card
    GET  /health                       — ChromaDB + Ollama status
    POST /ingest/refresh                — re-index changed docs

Run:
    uvicorn src.server:app --host 127.0.0.1 --port 8000
"""

import time
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.alerts import SplunkAlert
from src.card import RecommendationCard

# ponytail: heavy imports (LlamaIndex, ChromaDB, retrieval/scoring) deferred to
# lifespan/endpoints to avoid blocking module import. src.card/src.alerts are
# lightweight (pydantic models + stdlib only) and safe at top level.

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


# --- Endpoints ---

@app.post("/alert", response_model=RecommendationCard)
async def alert_endpoint(alert: SplunkAlert, generation: Optional[bool] = None):
    """
    Demo alert intake — accepts a synthetic Splunk-webhook-shaped alert
    (see src/alerts.py and data/sample_alerts/*.json), fingerprints it, and
    returns a RecommendationCard. Stands in for the real Splunk/ITRS event
    intake API until that integration is approved.

    `generation` query param overrides config/card.yaml's generation.enabled
    default for this request only (E3) — omit to use the config default.

    An identical recurring incident (same fingerprint signature_id) is served
    from src/recommendation_cache.py instead of re-running retrieval +
    scoring + LLM phrasing — see that module's docstring. Note: a cache hit
    returns whatever was cached regardless of this request's `generation`
    value (the cached card was already assembled once, under whatever
    generation setting was active then).
    """
    import uuid

    from src.alerts import build_alert_context
    from src.fingerprint import compute_fingerprint
    from src.recommendation import build_recommendation_card, apply_generation, GENERATION_ENABLED_DEFAULT
    from src import recommendation_cache

    start = time.perf_counter()
    correlation_id = str(uuid.uuid4())

    fp = compute_fingerprint(
        raw_text=alert.result.message,
        service=alert.result.service,
        environment=alert.result.environment,
        stack_trace=alert.result.stack_trace,
    )
    alert_context = build_alert_context(alert, fp)

    cached = recommendation_cache.get_cached(fp.signature_id)
    if cached is not None:
        elapsed = int((time.perf_counter() - start) * 1000)
        logger.info(f"[alert] {alert.search_name} | family={fp.error_family} | CACHE HIT #{cached.hit_count} | {elapsed}ms")
        cached_card = RecommendationCard.model_validate_json(cached.card_json)
        return cached_card.model_copy(update={"correlation_id": correlation_id})

    use_generation = GENERATION_ENABLED_DEFAULT if generation is None else generation
    card = build_recommendation_card(alert, fp, alert_context, correlation_id=correlation_id)
    if use_generation:
        card = apply_generation(card)

    recommendation_cache.store(
        signature_id=fp.signature_id,
        error_family=fp.error_family,
        service=alert.result.service,
        card_json=card.model_dump_json(),
    )

    elapsed = int((time.perf_counter() - start) * 1000)
    logger.info(f"[alert] {alert.search_name} | family={fp.error_family} | band={card.confidence.band} | {elapsed}ms")

    return card


class FeedbackRequest(BaseModel):
    """
    Echoes the card fields feedback.db needs (signature_id, error_family,
    recommended_runbook) — the client already has these from the /alert
    response; there is no server-side "cards by correlation_id" store to look
    them up from (correlation_id is a fresh UUID per /alert call, not
    persisted anywhere retrievable by itself — introducing one would mean a
    knowledge-plane lookup service just to support the decision plane, which
    R6 asks to keep separate).
    """
    signature_id: str
    error_family: Optional[str] = None
    recommended_runbook: Optional[str] = None
    decision: str
    actor: str
    comment: Optional[str] = None
    edited_action: Optional[str] = None


@app.post("/cards/{correlation_id}/feedback")
async def submit_feedback(correlation_id: str, req: FeedbackRequest):
    """
    Record an ops decision (accept/edit/reject/escalate/kb_gap) on a card.
    Persists to feedback.db (append-only, G1-G4) and routes to the configured
    TicketClient (H) — 'noop' by default, logs only, no network call.
    """
    from src.feedback import record_feedback, FeedbackValidationError
    from src.ticket_client import get_ticket_client

    try:
        record = record_feedback(
            correlation_id=correlation_id,
            signature_id=req.signature_id,
            error_family=req.error_family,
            recommended_runbook=req.recommended_runbook,
            decision=req.decision,
            actor=req.actor,
            comment=req.comment,
            edited_action=req.edited_action,
        )
    except FeedbackValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    client = get_ticket_client()
    if req.decision in ("accept", "edit", "reject", "escalate"):
        summary = f"[{req.decision}] by {req.actor}"
        if req.comment:
            summary += f": {req.comment}"
        if req.decision == "edit" and req.edited_action:
            summary += f" | edited action: {req.edited_action}"
        client.add_comment(req.signature_id, summary)
    elif req.decision == "kb_gap":
        client.create_kb_gap({
            "correlation_id": correlation_id,
            "signature_id": req.signature_id,
            "error_family": req.error_family,
            "recommended_runbook": req.recommended_runbook,
            "actor": req.actor,
            "comment": req.comment,
        })

    logger.info(f"[feedback] correlation_id={correlation_id} decision={req.decision} actor={req.actor}")

    return {"status": "recorded", "id": record.id, "decided_at": record.decided_at}


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
