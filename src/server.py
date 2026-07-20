"""
FastAPI persistent service — loads LlamaIndex, ChromaDB, BM25, and Ollama once at startup.
Queries hit a warm index. No cold-start penalty per request.

Endpoints:
    POST /query          — retrieve + optional generation (JSON response)
    POST /query/stream   — streaming generation (Server-Sent Events)
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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ponytail: heavy imports (LlamaIndex, ChromaDB) deferred to lifespan/endpoints
# to avoid blocking module import. Only stdlib + fastapi + pydantic at top level.

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("llmkb2")

_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load LlamaIndex settings, ChromaDB index, BM25 index, and service graph once at startup."""
    import asyncio
    from src.config import init_llama_index_settings
    from src.indexer import load_index
    from src.retrieval import get_bm25
    from src.graph import get_service_graph

    loop = asyncio.get_event_loop()
    # ponytail: run all blocking I/O (ChromaDB + BM25 corpus load) off the event loop
    # so uvicorn can complete startup handshake without stalling.
    await loop.run_in_executor(None, init_llama_index_settings)
    _state["index"] = await loop.run_in_executor(None, load_index)
    await loop.run_in_executor(None, get_bm25)
    await loop.run_in_executor(None, get_service_graph)
    logger.info("Startup complete: index + BM25 + service graph loaded")
    yield
    _state.clear()


app = FastAPI(title="LLMKB2 — AIOps Runbook Assistant", lifespan=lifespan)


# --- Models ---

class QueryRequest(BaseModel):
    question: str
    doc_type: Optional[str] = None
    service: Optional[str] = None
    severity: Optional[str] = None
    top_k: int = 8
    no_generate: bool = False


class Citation(BaseModel):
    doc_id: str
    doc_type: str
    section: str
    service: str
    score: float
    score_explain: Optional[dict[str, Any]] = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    latency_ms: int


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

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest):
    """Retrieve (with ID routing + hybrid) and optionally generate an answer."""
    start = time.perf_counter()

    from src.query import retrieve_only, build_query_engine
    from src.retrieval import is_id_lookup

    if req.no_generate:
        nodes = retrieve_only(
            req.question, top_k=req.top_k,
            doc_type=req.doc_type, service=req.service, severity=req.severity,
        )
        answer = "(retrieval only)"
        mode = "retrieve"
    else:
        engine = build_query_engine(
            top_k=req.top_k, query=req.question, doc_type=req.doc_type,
            service=req.service, severity=req.severity,
        )
        response = engine.query(req.question)
        answer = str(response)
        nodes = response.source_nodes
        mode = "id" if is_id_lookup(req.question) else "rag"

    elapsed = int((time.perf_counter() - start) * 1000)
    logger.info(f"[{mode}] \"{req.question[:60]}\" | {elapsed}ms | {len(nodes)} results")

    return QueryResponse(answer=answer, citations=_citations(nodes), latency_ms=elapsed)


@app.post("/query/stream")
async def query_stream(req: QueryRequest):
    """Stream the answer token-by-token via Server-Sent Events (first token in ~2s)."""
    from src.query import build_query_engine

    def generate():
        start = time.perf_counter()
        engine = build_query_engine(
            top_k=req.top_k, query=req.question, doc_type=req.doc_type,
            service=req.service, severity=req.severity, streaming=True,
        )
        response = engine.query(req.question)
        for token in response.response_gen:
            yield token
        elapsed = int((time.perf_counter() - start) * 1000)
        # Trailing citation summary
        ids = ", ".join(n.node.metadata.get("id", "?") for n in response.source_nodes[:5])
        yield f"\n\n---\nSources: {ids}\nLatency: {elapsed}ms\n"
        logger.info(f"[stream] \"{req.question[:60]}\" | {elapsed}ms")

    return StreamingResponse(generate(), media_type="text/plain")


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
    """Re-ingest changed documents, reload the index, BM25, and service graph."""
    from src.ingest import run_ingestion
    from src.indexer import load_index
    from src.retrieval import reset_bm25, get_bm25
    from src.graph import reset_graph, get_service_graph

    stats = run_ingestion(force=False, local=False)
    _state["index"] = load_index()
    reset_bm25()
    get_bm25()  # rebuild
    reset_graph()
    get_service_graph()  # rebuild
    return {"status": "refreshed", "stats": stats}


# --- Graph endpoints ---

@app.get("/graph/stats")
async def graph_stats():
    """Return service dependency graph summary statistics."""
    from src.graph import get_service_graph
    graph = get_service_graph()
    return graph.get_stats()


@app.get("/graph/blast-radius/{service}")
async def blast_radius(service: str, depth: int = 2):
    """
    Return services affected if the given service goes down.
    depth: BFS traversal depth (default 2).
    """
    from src.graph import get_service_graph
    graph = get_service_graph()
    affected = graph.affected_by(service, depth=depth)
    return {
        "service": service,
        "depth": depth,
        "affected": affected,
        "affected_count": len(affected),
    }


@app.get("/graph/service/{service}")
async def service_info(service: str):
    """Return incidents and runbooks associated with a service."""
    from src.graph import get_service_graph
    graph = get_service_graph()
    return {
        "service": service,
        "incidents": graph.incidents_for(service),
        "runbooks": graph.runbooks_for(service),
    }


# --- Sub-question endpoint (for complex multi-part queries) ---

class SubQueryRequest(BaseModel):
    question: str
    top_k: int = 8


@app.post("/query/sub")
async def sub_question_query(req: SubQueryRequest):
    """
    Decompose a complex query into sub-questions, retrieve independently, then synthesize.
    Best for comparison/analysis queries like 'Compare INC-005 root cause with INC-008'.
    """
    from src.query import build_sub_question_engine
    import time as _time

    start = _time.perf_counter()
    engine = build_sub_question_engine(top_k=req.top_k)
    response = engine.query(req.question)
    elapsed = int((_time.perf_counter() - start) * 1000)

    return {
        "answer": str(response),
        "latency_ms": elapsed,
    }
