"""
LlamaIndex Query Engine — config-driven multi-signal scoring with hybrid retrieval.

Pipeline:
  1. ID lookup (INC-003)  -> direct metadata fetch, no embedding (fast path)
  2. Everything else      -> auto-filter inference -> hybrid candidates (dense + BM25)
                          -> cross-encoder rerank -> multi-signal scoring

Scoring signals (weights in config/scoring.yaml):
  A. RRF fused rank from dense + BM25 retrieval
  B. Exact text match (query terms found in node text)
  C. Metadata field match (service mentioned in query matches node)
  D. Section relevance (action vs info query intent)
  E. Penalty for low-value sections (links, revision-history)
  F. Cross-encoder semantic relevance (neural reranker)

Auto-retrieval: LLM infers metadata filters from natural language queries.
  No more --service/--type/--severity flags needed (kept as manual overrides).

Usage:
    python -m src.query "payment service pods are OOMKilled what do I do"
    python -m src.query "INC-003" --no-generate
    python -m src.query "how to fix connection pool exhaustion" --service reporting-service
    python -m src.query --interactive
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import re
import time
from collections import Counter
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table

from llama_index.core import PromptTemplate, get_response_synthesizer
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.retrievers import BaseRetriever, VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.vector_stores import (
    MetadataFilters,
    MetadataFilter,
    FilterOperator,
    FilterCondition,
)

from src.config import OLLAMA_MODEL, init_llama_index_settings
from src.indexer import load_index
from src.retrieval import CONFIG, is_id_lookup, id_lookup, hybrid_candidates, get_bm25

console = Console()

# --- Config-derived constants ---
WEIGHTS = CONFIG["weights"]
LOW_VALUE_SECTIONS = set(CONFIG["penalties"]["low_value_sections"])
PENALTY_LOW_VALUE = CONFIG["penalties"]["penalty_amount"]
CANDIDATE_MULT = CONFIG["thresholds"]["candidate_multiplier"]
MIN_CANDIDATE_COUNT = CONFIG["thresholds"].get("min_candidate_count", 50)
ATTACH_EXPLANATIONS = CONFIG.get("scoring", {}).get("attach_explanations", True)
MINMAX_NORMALIZE_FINAL = CONFIG.get("scoring", {}).get("minmax_normalize_final", False)
ACTION_KEYWORDS = set(CONFIG["intent_keywords"]["action"])
INFO_KEYWORDS = set(CONFIG["intent_keywords"]["info"])
ACTION_SECTIONS = set(CONFIG["action_sections"])
INFO_SECTIONS = set(CONFIG["info_sections"])
KNOWN_SERVICES = set(CONFIG["known_services"])
DOC_COHERENCE_CFG = CONFIG.get("doc_coherence", {})
DOC_COHERENCE_THRESHOLD = DOC_COHERENCE_CFG.get("threshold", 3)
DOC_COHERENCE_BOOST = DOC_COHERENCE_CFG.get("boost_per_chunk", 0.03)
DOC_COHERENCE_MAX_BOOST = DOC_COHERENCE_CFG.get("max_boost", 0.15)
DOC_TYPE_PRIORITY = CONFIG.get("doc_type_priority", {})

# Reranker config (cross-encoder)
RERANKER_CFG = CONFIG.get("reranker", {})
RERANKER_ENABLED = RERANKER_CFG.get("enabled", False)
RERANKER_MODEL = RERANKER_CFG.get("model", "cross-encoder/ms-marco-MiniLM-L-2-v2")
RERANKER_TOP_N = RERANKER_CFG.get("top_n", 25)

# Auto-retrieval config
AUTO_RETRIEVAL_CFG = CONFIG.get("auto_retrieval", {})
AUTO_RETRIEVAL_ENABLED = AUTO_RETRIEVAL_CFG.get("enabled", False)


def candidate_count_for(top_k: int) -> int:
    """Use a wider reranking pool than the final result count."""
    return max(MIN_CANDIDATE_COUNT, top_k * CANDIDATE_MULT)


def tokenize_for_match(text: str) -> list[str]:
    """Tokenize query/content for exact-match features without substring false positives."""
    return re.findall(r"[a-z0-9\-]+", text.lower())


# --- Custom SRE Prompt Template ---
SRE_QA_PROMPT_TMPL = """\
You are an SRE assistant answering questions from an operational knowledge base.
Your answers are grounded ONLY in the provided context. If the context doesn't contain enough info, say so.
Be specific: include commands, service names, and concrete steps when available.
Always cite which document(s) your answer draws from using their document IDs.

Context from knowledge base:
-----
{context_str}
-----

Question: {query_str}

Answer the question based on the context above. Include specific commands or steps if available. Cite the source document IDs."""

SRE_QA_PROMPT = PromptTemplate(SRE_QA_PROMPT_TMPL)


# --- Multi-Signal Scorer (config-driven) ---
class MultiSignalScorer(BaseNodePostprocessor):
    """Combine RRF, exact, metadata, and section signals into an explainable score."""

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> list[NodeWithScore]:
        if not nodes or query_bundle is None:
            return nodes

        query_lower = query_bundle.query_str.lower()
        query_tokens = tokenize_for_match(query_lower)
        query_words = set(query_tokens)

        # Precompute IDF weights for query tokens (used by exact match signal)
        bm25_idf = get_bm25().idf
        idf_total = sum(bm25_idf.get(w, 1.0) for w in query_words) if query_words else 1.0

        is_action_query = bool(query_words & ACTION_KEYWORDS)
        is_info_query = bool(query_words & INFO_KEYWORDS)

        # Detect a service mention in the query
        query_service = None
        for svc in KNOWN_SERVICES:
            parts = [p for p in svc.split("-") if p not in ("service", "gateway", "general", "all")]
            if any(p in query_lower for p in parts):
                query_service = svc
                break

        for nws in nodes:
            text_lower = nws.node.get_content().lower()
            metadata = nws.node.metadata or {}
            section_name = metadata.get("section_name", "")
            doc_type = metadata.get("doc_type", "")
            node_service = metadata.get("service", "")
            retrieval = dict(metadata.get("_retrieval") or {})

            # Retrieval features. RRF is preferred; dense score is kept as fallback for
            # any legacy vector-only path that has not gone through hybrid_candidates().
            semantic_score = nws.score or 0
            rrf_score = retrieval.get("rrf_score")
            if rrf_score is None:
                rrf_score = semantic_score

            # Signal B: exact text match (IDF-weighted)
            if query_lower in text_lower:
                exact_score = 1.0
            else:
                text_words = set(tokenize_for_match(text_lower))
                weighted_hits = sum(bm25_idf.get(w, 1.0) for w in query_words if w in text_words)
                exact_score = (weighted_hits / idf_total) if idf_total > 0 else 0.0

            # Signal C: metadata field match
            metadata_score = 0.0
            if query_service:
                if query_service == node_service:
                    metadata_score = 1.0
                elif any(p in node_service for p in query_service.split("-") if p not in ("service", "gateway")):
                    metadata_score = 0.7

            # Signal D: section relevance
            section_score = 0.0
            if is_action_query:
                if section_name in ACTION_SECTIONS:
                    section_score = 1.0
                elif doc_type == "runbook":
                    section_score = 0.8
            elif is_info_query:
                if section_name in INFO_SECTIONS:
                    section_score = 1.0

            # Signal E: doc_type authority tier (runbook > incident > system > informal)
            doc_priority_score = DOC_TYPE_PRIORITY.get(doc_type, 0.1)

            combined = (
                WEIGHTS["rrf"] * rrf_score
                + WEIGHTS["exact_match"] * exact_score
                + WEIGHTS["metadata_match"] * metadata_score
                + WEIGHTS["section_relevance"] * section_score
                + WEIGHTS.get("doc_type_priority", 0.10) * doc_priority_score
            )

            penalty = 0.0
            if section_name in LOW_VALUE_SECTIONS:
                penalty = PENALTY_LOW_VALUE
                combined -= penalty

            nws.score = max(combined, 0.0)

            if ATTACH_EXPLANATIONS:
                metadata["_score_explain"] = {
                    "final_score": round(nws.score or 0.0, 6),
                    "weights": {
                        "rrf": WEIGHTS["rrf"],
                        "exact_match": WEIGHTS["exact_match"],
                        "metadata_match": WEIGHTS["metadata_match"],
                        "section_relevance": WEIGHTS["section_relevance"],
                        "doc_type_priority": WEIGHTS.get("doc_type_priority", 0.10),
                    },
                    "retrieval": {
                        "rrf_score": round(float(rrf_score or 0.0), 6),
                        "rrf_k": retrieval.get("rrf_k"),
                        "rrf_normalized": retrieval.get("rrf_normalized"),
                        "dense_rank": retrieval.get("dense_rank"),
                        "dense_score": retrieval.get("dense_score"),
                        "bm25_rank": retrieval.get("bm25_rank"),
                        "bm25_score": retrieval.get("bm25_score"),
                    },
                    "signals": {
                        "exact_match": round(exact_score, 6),
                        "metadata_match": round(metadata_score, 6),
                        "section_relevance": round(section_score, 6),
                        "doc_type_priority": round(doc_priority_score, 6),
                    },
                    "penalties": {
                        "low_value_section": round(penalty, 6),
                    },
                    "context": {
                        "section_name": section_name,
                        "doc_type": doc_type,
                        "query_service": query_service,
                        "node_service": node_service,
                    },
                }
                nws.node.metadata = metadata

        # Document-level coherence boost: reward chunks from docs with multiple hits
        doc_counts = Counter(
            (nws.node.metadata or {}).get("id", "")
            for nws in nodes
            if (nws.node.metadata or {}).get("id")
        )
        for nws in nodes:
            doc_id = (nws.node.metadata or {}).get("id", "")
            count = doc_counts.get(doc_id, 0)
            if count >= DOC_COHERENCE_THRESHOLD:
                boost = min(count * DOC_COHERENCE_BOOST, DOC_COHERENCE_MAX_BOOST)
                nws.score = (nws.score or 0.0) + boost
                if ATTACH_EXPLANATIONS:
                    meta = nws.node.metadata or {}
                    explain = meta.get("_score_explain") or {}
                    explain.setdefault("penalties", {})["doc_coherence_boost"] = round(boost, 6)
                    explain["final_score"] = round(nws.score, 6)
                    meta["_score_explain"] = explain
                    nws.node.metadata = meta

        # Raw final scores are used for ranking. Optional min-max is retained only
        # as a config-controlled compatibility switch, not the default behavior.
        if MINMAX_NORMALIZE_FINAL:
            scores = [n.score for n in nodes]
            min_s, max_s = min(scores), max(scores)
            spread = max_s - min_s
            if spread > 0:
                for n in nodes:
                    n.score = (n.score - min_s) / spread
            else:
                for n in nodes:
                    n.score = 1.0

        nodes.sort(key=lambda n: n.score or 0, reverse=True)
        return nodes


# --- Cross-Encoder Reranker ---
_reranker = None


def get_reranker():
    """Lazy-load the cross-encoder reranker (downloads model on first use)."""
    global _reranker
    if _reranker is None and RERANKER_ENABLED:
        try:
            from llama_index.postprocessor.sbert_rerank import SentenceTransformerRerank
            _reranker = SentenceTransformerRerank(
                model=RERANKER_MODEL,
                top_n=RERANKER_TOP_N,
            )
            console.print(f"[dim]Reranker loaded: {RERANKER_MODEL}[/]")
        except ImportError:
            console.print("[yellow]sbert-rerank not installed. Run: pip install llama-index-postprocessor-sbert-rerank[/]")
            return None
    return _reranker


# --- Auto-Retrieval (LLM-inferred metadata filters) ---
def auto_infer_filters(query: str) -> Optional[MetadataFilters]:
    """
    Use the configured LLM to infer metadata filters from a natural language query.

    The LLM analyzes the query and extracts structured filters for:
      - service: which service the query is about
      - doc_type: preferred document type (runbook, incident, system)
      - severity: incident severity level

    Returns None if no filters can be confidently inferred.
    """
    if not AUTO_RETRIEVAL_ENABLED:
        return None

    from llama_index.core import Settings
    import json as json_mod

    services_list = ", ".join(sorted(KNOWN_SERVICES - {"general", "all"}))
    doc_types_list = ", ".join(sorted(DOC_TYPE_PRIORITY.keys()))

    prompt = f"""Analyze this SRE query and extract metadata filters. Return ONLY a JSON object with the fields you can confidently identify. If unsure about a field, omit it entirely.

Available services: {services_list}
Available doc_types: {doc_types_list}
Available severities: SEV1, SEV2, SEV3

Query: "{query}"

Return a JSON object like: {{"service": "...", "doc_type": "...", "severity": "..."}}
Only include fields you are confident about. Return {{}} if no filters apply.
JSON:"""

    try:
        llm = Settings.llm
        response = str(llm.complete(prompt)).strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```" in response:
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
            response = response.strip()

        # Find the JSON object in the response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start == -1 or end == 0:
            return None

        parsed = json_mod.loads(response[start:end])
        if not parsed:
            return None

        filters = []
        if parsed.get("service") and parsed["service"] not in ("general", "all", "unknown"):
            svc = str(parsed["service"]).lower()
            if svc in KNOWN_SERVICES:
                filters.append(MetadataFilter(key="service", value=svc, operator=FilterOperator.EQ))
        if parsed.get("doc_type") and parsed["doc_type"] in DOC_TYPE_PRIORITY:
            filters.append(MetadataFilter(key="doc_type", value=parsed["doc_type"], operator=FilterOperator.EQ))
        if parsed.get("severity") and parsed["severity"].upper().startswith("SEV"):
            filters.append(MetadataFilter(key="severity", value=parsed["severity"].upper(), operator=FilterOperator.EQ))

        if not filters:
            return None

        console.print(f"[dim]Auto-filters: {', '.join(f'{f.key}={f.value}' for f in filters)}[/]")
        return MetadataFilters(filters=filters, condition=FilterCondition.AND)

    except Exception as e:
        # Auto-retrieval is best-effort; fall through to unfiltered retrieval
        console.print(f"[dim]Auto-filter inference failed (falling back to unfiltered): {e}[/]")
        return None


class HybridRetriever(BaseRetriever):
    """LlamaIndex retriever wrapper that returns RRF-fused hybrid candidates,
    optionally reranked by a cross-encoder before multi-signal scoring."""

    def __init__(self, vector_retriever: VectorIndexRetriever, candidate_count: int, top_k: int):
        super().__init__()
        self.vector_retriever = vector_retriever
        self.candidate_count = candidate_count
        self.top_k = top_k
        self.scorer = MultiSignalScorer()

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        pool = hybrid_candidates(
            query_bundle.query_str,
            self.vector_retriever,
            candidate_count=self.candidate_count,
        )

        # Cross-encoder rerank: provides semantic relevance before heuristic scoring
        reranker = get_reranker()
        if reranker is not None:
            pool = reranker.postprocess_nodes(pool, query_bundle=query_bundle)

        ranked = self.scorer.postprocess_nodes(pool, query_bundle=query_bundle)
        return ranked[:self.top_k]


# --- Filter Builder ---
def build_metadata_filters(
    query: Optional[str] = None,
    doc_type: Optional[str] = None,
    service: Optional[str] = None,
    severity: Optional[str] = None,
) -> Optional[MetadataFilters]:
    """
    Build LlamaIndex MetadataFilters.

    Priority:
      1. Explicit CLI/API overrides (doc_type, service, severity)
      2. LLM auto-inferred filters from query text (if auto_retrieval enabled)
      3. None (no filtering)
    """
    # Explicit overrides always take priority
    filters = []
    if doc_type:
        filters.append(MetadataFilter(key="doc_type", value=doc_type, operator=FilterOperator.EQ))
    if service:
        filters.append(MetadataFilter(key="service", value=service.lower(), operator=FilterOperator.EQ))
    if severity:
        filters.append(MetadataFilter(key="severity", value=severity.upper(), operator=FilterOperator.EQ))
    if filters:
        return MetadataFilters(filters=filters, condition=FilterCondition.AND)

    # Fall back to auto-inferred filters
    if query and AUTO_RETRIEVAL_ENABLED:
        return auto_infer_filters(query)

    return None


# --- Core retrieval (ID routing + hybrid) ---
def retrieve_only(
    query: str,
    top_k: int = 8,
    doc_type: Optional[str] = None,
    service: Optional[str] = None,
    severity: Optional[str] = None,
) -> list:
    """
    Retrieve nodes without LLM generation.
    Routes ID lookups to a direct metadata fetch (no embedding);
    everything else uses hybrid (dense + BM25) candidates + cross-encoder
    rerank + multi-signal scoring.
    """
    # Fast path: ID lookup — no embedding, no vector search
    if is_id_lookup(query):
        return id_lookup(query, top_k=top_k)

    index = load_index()
    metadata_filters = build_metadata_filters(query, doc_type, service, severity)

    retriever = VectorIndexRetriever(
        index=index,
        similarity_top_k=candidate_count_for(top_k),
        filters=metadata_filters,
    )

    pool = hybrid_candidates(query, retriever, candidate_count=candidate_count_for(top_k))

    # Cross-encoder rerank before scoring
    query_bundle = QueryBundle(query_str=query)
    reranker = get_reranker()
    if reranker is not None:
        pool = reranker.postprocess_nodes(pool, query_bundle=query_bundle)

    scorer = MultiSignalScorer()
    ranked = scorer.postprocess_nodes(pool, query_bundle=query_bundle)
    return ranked[:top_k]


# --- Query Engine Builder (for generation) ---
def build_query_engine(
    top_k: int = 8,
    query: Optional[str] = None,
    doc_type: Optional[str] = None,
    service: Optional[str] = None,
    severity: Optional[str] = None,
    streaming: bool = False,
):
    """Build a RetrieverQueryEngine with hybrid retrieval + reranking + multi-signal scoring."""
    index = load_index()
    metadata_filters = build_metadata_filters(query, doc_type, service, severity)

    retriever = VectorIndexRetriever(
        index=index,
        similarity_top_k=candidate_count_for(top_k),
        filters=metadata_filters,
    )

    response_synthesizer = get_response_synthesizer(
        text_qa_template=SRE_QA_PROMPT,
        streaming=streaming,
    )

    return RetrieverQueryEngine(
        retriever=HybridRetriever(retriever, candidate_count=candidate_count_for(top_k), top_k=top_k),
        response_synthesizer=response_synthesizer,
    )


def build_sub_question_engine(top_k: int = 8):
    """
    Build a SubQuestionQueryEngine that decomposes complex queries into sub-questions.

    Best for comparison/analysis queries:
      - "Compare INC-005 root cause with INC-008"
      - "What runbooks cover both disk and memory issues?"
      - "Show all incidents related to payment-gateway and their resolutions"

    The engine decomposes the query, retrieves each sub-question independently
    using the full hybrid pipeline, then synthesizes a combined answer.
    """
    from llama_index.core.tools import QueryEngineTool
    from llama_index.core.query_engine import SubQuestionQueryEngine

    base_engine = build_query_engine(top_k=top_k)

    kb_tool = QueryEngineTool.from_defaults(
        query_engine=base_engine,
        name="sre_knowledge_base",
        description=(
            "Search the SRE operational knowledge base containing incidents, "
            "runbooks, system architecture docs, and governance policies. "
            "Use this tool for any question about services, incidents, outages, "
            "runbooks, or operational procedures."
        ),
    )

    # ponytail: single tool is sufficient — SubQuestionQueryEngine shines most
    # when there are multiple distinct sources. With one source, it still helps
    # for multi-part queries by retrieving each sub-question independently.
    return SubQuestionQueryEngine.from_defaults(
        query_engine_tools=[kb_tool],
        use_async=False,  # sync: Ollama is blocking anyway
        verbose=False,
    )


# --- Display ---
def display_results(answer: str, source_nodes: list) -> None:
    """Display the answer and citations in a rich format."""
    if answer:
        console.print(Panel(Markdown(answer), title="[bold green]Answer[/]", border_style="green"))

    if not source_nodes:
        return

    table = Table(title="Citations")
    table.add_column("#", style="dim", width=3)
    table.add_column("Doc ID", style="cyan", width=12)
    table.add_column("Type", style="magenta", width=10)
    table.add_column("Section", style="yellow", width=20)
    table.add_column("Service", width=18)
    table.add_column("Score", width=10)
    table.add_column("DocPri", width=7)
    table.add_column("RRF", width=8)
    table.add_column("Dense", width=7)
    table.add_column("BM25", width=7)

    for i, nws in enumerate(source_nodes[:8], 1):
        m = nws.node.metadata or {}
        explain = m.get("_score_explain") or {}
        retrieval = explain.get("retrieval") or m.get("_retrieval") or {}
        signals = explain.get("signals") or {}
        table.add_row(
            str(i), str(m.get("id", "?")), m.get("doc_type", "?"),
            m.get("section_name", "?"), m.get("service", "?"),
            f"{(nws.score or 0):.4f}",
            f"{signals.get('doc_type_priority', DOC_TYPE_PRIORITY.get(m.get('doc_type', ''), 0.1)):.2f}",
            f"{retrieval.get('rrf_score', 0):.4f}" if retrieval.get("rrf_score") is not None else "?",
            str(retrieval.get("dense_rank") or "-"),
            str(retrieval.get("bm25_rank") or "-"),
        )
    console.print(table)


# --- Main CLI ---
def main():
    parser = argparse.ArgumentParser(
        description="LLMKB2 — Query the Knowledge Base (Hybrid Retrieval + Multi-Signal Scoring)"
    )
    parser.add_argument("question", nargs="?", help="Your question")
    parser.add_argument("--type", type=str, default=None, help="Filter by doc type")
    parser.add_argument("--service", type=str, default=None, help="Filter by service name")
    parser.add_argument("--severity", type=str, default=None, help="Filter by severity")
    parser.add_argument("--top-k", type=int, default=8, help="Chunks to retrieve (default: 8)")
    parser.add_argument("--no-generate", action="store_true", help="Retrieve only, no LLM")
    parser.add_argument("--stream", action="store_true", help="Stream response tokens")
    parser.add_argument("--interactive", action="store_true", help="Interactive query mode")
    parser.add_argument("--sub", action="store_true",
                        help="Use SubQuestionQueryEngine for complex multi-part queries")
    parser.add_argument("--blast-radius", type=str, default=None,
                        help="Show blast radius for a service (e.g., --blast-radius payment-gateway)")
    args = parser.parse_args()

    init_llama_index_settings()

    # Blast-radius graph query (no LLM needed)
    if args.blast_radius:
        from src.graph import get_service_graph
        graph = get_service_graph()
        affected = graph.affected_by(args.blast_radius)
        console.print(f"\n[bold]Blast radius for:[/] {args.blast_radius}")
        if affected:
            for svc, evidence in sorted(affected.items()):
                console.print(f"  → {svc}  [dim](evidence: {', '.join(evidence[:3])})[/]")
        else:
            console.print("  (no related services found in graph)")
        console.print()
        return

    if args.interactive:
        console.print(f"[bold]LLMKB2 Interactive Mode[/] (Hybrid + Multi-Signal | model: {OLLAMA_MODEL})")
        console.print("Type 'quit' to exit\n")
        while True:
            try:
                question = console.input("[bold cyan]Question:[/] ")
            except (KeyboardInterrupt, EOFError):
                break
            if question.lower() in ("quit", "exit", "q"):
                break
            if not question.strip():
                continue
            _run_query(question, args)
            console.print()
        return

    if not args.question:
        parser.print_help()
        sys.exit(1)

    console.print(f"\n[bold]Query:[/] {args.question}")
    console.print(f"[dim]Model: {OLLAMA_MODEL} | Hybrid + Multi-Signal[/]\n")
    _run_query(args.question, args)


def _run_query(question: str, args):
    """Execute one query honoring the no-generate / stream / sub flags, print latency."""
    # ID lookups and --no-generate never call the LLM
    if args.no_generate or is_id_lookup(question):
        t0 = time.perf_counter()
        nodes = retrieve_only(question, top_k=args.top_k,
                              doc_type=args.type, service=args.service, severity=args.severity)
        elapsed = time.perf_counter() - t0
        if not nodes:
            console.print("[yellow]No relevant chunks found. Run: python -m src.ingest --local[/]")
            return
        label = "(ID lookup)" if is_id_lookup(question) and not args.no_generate else "(generation skipped)"
        display_results(label, nodes)
        console.print(f"\n[dim]Latency: {elapsed:.2f}s[/]")
        return

    # Sub-question engine for complex multi-part queries
    if getattr(args, "sub", False):
        t0 = time.perf_counter()
        qe = build_sub_question_engine(top_k=args.top_k)
        response = qe.query(question)
        elapsed = time.perf_counter() - t0
        console.print(Panel(Markdown(str(response)), title="[bold green]Answer (Sub-Question)[/]", border_style="green"))
        console.print(f"\n[dim]Latency: {elapsed:.2f}s[/]")
        return

    # Generation path (streaming)
    t0 = time.perf_counter()
    qe = build_query_engine(top_k=args.top_k, query=question, doc_type=args.type,
                            service=args.service, severity=args.severity, streaming=True)
    response = qe.query(question)
    console.print("[bold green]Answer:[/]")
    for token in response.response_gen:
        console.print(token, end="")
    console.print("\n")
    elapsed = time.perf_counter() - t0
    display_results("", response.source_nodes)
    console.print(f"\n[dim]Latency: {elapsed:.2f}s[/]")


if __name__ == "__main__":
    main()
