"""
LlamaIndex Query Engine — config-driven multi-signal scoring with hybrid retrieval.

Library module powering src/server.py's POST /alert: build_query_engine() takes an
alert-derived query string + explicit service filter, runs hybrid (dense + BM25)
candidate retrieval, cross-encoder rerank, and multi-signal scoring, then generates
a grounded answer.

Scoring signals (weights in config/scoring.yaml):
  A. RRF fused rank from dense + BM25 retrieval
  B. Exact text match (query terms found in node text)
  C. Metadata field match (service mentioned in query matches node)
  D. Section relevance (action vs info query intent)
  E. Penalty for low-value sections (links, revision-history)
  F. Cross-encoder semantic relevance (neural reranker)
"""

import logging
import re
from collections import Counter
from typing import Optional

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

from src.indexer import load_index
from src.retrieval import CONFIG, hybrid_candidates, get_bm25

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
            logging.getLogger("llmkb2").info(f"Reranker loaded: {RERANKER_MODEL}")
        except ImportError:
            logging.getLogger("llmkb2").warning(
                "sbert-rerank not installed. Run: pip install llama-index-postprocessor-sbert-rerank"
            )
            return None
    return _reranker


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
    doc_type: Optional[str] = None,
    service: Optional[str] = None,
    severity: Optional[str] = None,
) -> Optional[MetadataFilters]:
    """
    Build LlamaIndex MetadataFilters from explicit overrides (doc_type, service, severity).
    Returns None if none are given.
    """
    filters = []
    if doc_type:
        filters.append(MetadataFilter(key="doc_type", value=doc_type, operator=FilterOperator.EQ))
    if service:
        filters.append(MetadataFilter(key="service", value=service.lower(), operator=FilterOperator.EQ))
    if severity:
        filters.append(MetadataFilter(key="severity", value=severity.upper(), operator=FilterOperator.EQ))
    if filters:
        return MetadataFilters(filters=filters, condition=FilterCondition.AND)
    return None


# --- Query Engine Builder (for generation) ---
def build_query_engine(
    top_k: int = 8,
    doc_type: Optional[str] = None,
    service: Optional[str] = None,
    severity: Optional[str] = None,
):
    """Build a RetrieverQueryEngine with hybrid retrieval + reranking + multi-signal scoring."""
    index = load_index()
    metadata_filters = build_metadata_filters(doc_type, service, severity)

    retriever = VectorIndexRetriever(
        index=index,
        similarity_top_k=candidate_count_for(top_k),
        filters=metadata_filters,
    )

    response_synthesizer = get_response_synthesizer(text_qa_template=SRE_QA_PROMPT)

    return RetrieverQueryEngine(
        retriever=HybridRetriever(retriever, candidate_count=candidate_count_for(top_k), top_k=top_k),
        response_synthesizer=response_synthesizer,
    )
