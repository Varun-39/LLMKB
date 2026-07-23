"""
LlamaIndex Query Engine — config-driven multi-signal scoring with hybrid retrieval.

Library module powering retrieve_only(): takes a query string (with an optional
structured AlertContext) and runs hybrid (dense + BM25) candidate retrieval
(recall stage), optional cross-encoder narrowing, and deterministic multi-signal
scoring (ranking stage) — no LLM call happens in this module. src/recommendation.py's
build_recommendation_card() consumes retrieve_only()'s output to assemble a
RecommendationCard; any LLM phrasing pass happens separately, afterward, via that
module's apply_generation().

Scoring signals (config/scoring.yaml's `signals`) — the deck's 4, plus
section_relevance retained as an auxiliary 5th:
  A. exact_error_match  — structured error_family match, else IDF text overlap
  B. component_match    — structured service/component match
  C. source_quality     — doc_type authority tier
  D. past_fix_success   — outcomes.db cohort ratio for the candidate's runbook
  E. section_relevance  — section type vs. query intent (auxiliary, additive)

RRF (dense+BM25 fusion, src/retrieval.py) builds the candidate POOL — the recall
stage. It is NOT one of the signals above and does not contribute to `combined`:
recall (did we find the right doc) and ranking (did we order it right) are kept
separate so a miss can be attributed to one stage or the other. rrf_score is
still recorded in _score_explain for audit.
"""

import logging
import re
from collections import Counter
from typing import Optional

from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.retrievers import BaseRetriever, VectorIndexRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.vector_stores import (
    MetadataFilters,
    MetadataFilter,
    FilterOperator,
    FilterCondition,
)

from src.alerts import AlertContext
from src.indexer import load_index
from src.outcomes import CONFIG as CONFIDENCE_CONFIG, cohort_counts
from src.retrieval import CONFIG, hybrid_candidates, get_bm25

# --- Config-derived constants ---
SIGNALS_CFG = CONFIG["signals"]
LOW_VALUE_SECTIONS = set(CONFIG["penalties"]["low_value_sections"])
PENALTY_LOW_VALUE = CONFIG["penalties"]["penalty_amount"]
CANDIDATE_MULT = CONFIG["thresholds"]["candidate_multiplier"]
MIN_CANDIDATE_COUNT = CONFIG["thresholds"].get("min_candidate_count", 50)
FINAL_TOP_K_DEFAULT = CONFIG.get("candidate_pool", {}).get("final_top_k", 8)
ATTACH_EXPLANATIONS = CONFIG.get("scoring", {}).get("attach_explanations", True)
MINMAX_NORMALIZE_FINAL = CONFIG.get("scoring", {}).get("minmax_normalize_final", False)
ACTION_KEYWORDS = set(CONFIG["intent_keywords"]["action"])
INFO_KEYWORDS = set(CONFIG["intent_keywords"]["info"])
ACTION_SECTIONS = set(CONFIG["action_sections"])
INFO_SECTIONS = set(CONFIG["info_sections"])
# Deterministic order (config file order) for the text-detection fallback below —
# a plain set's iteration order is randomized per-process (PYTHONHASHSEED), which
# previously made manual-query service detection nondeterministic.
KNOWN_SERVICES_ORDERED = list(CONFIG["known_services"])
KNOWN_SERVICES = set(KNOWN_SERVICES_ORDERED)
DOC_COHERENCE_CFG = CONFIG.get("doc_coherence", {})
DOC_COHERENCE_THRESHOLD = DOC_COHERENCE_CFG.get("threshold", 3)
DOC_COHERENCE_BOOST = DOC_COHERENCE_CFG.get("boost_per_chunk", 0.03)
DOC_COHERENCE_MAX_BOOST = DOC_COHERENCE_CFG.get("max_boost", 0.15)
SOURCE_QUALITY_TIERS = CONFIG.get("source_quality_tiers", {})

RETRIEVAL_FILTERS_CFG = CONFIG.get("retrieval_filters", {})
SERVICE_FILTER_MODE = RETRIEVAL_FILTERS_CFG.get("service_filter_mode", "strict")
ERROR_FAMILY_FILTER_MODE = RETRIEVAL_FILTERS_CFG.get("error_family_filter_mode", "soft")

EXPLANATIONS_CFG = CONFIG.get("explanations", {})
EXPLANATIONS_ENABLED = EXPLANATIONS_CFG.get("enabled", True)
EXPLANATION_TEMPLATES = EXPLANATIONS_CFG.get("templates", {})

# Confidence config's cohort-counting rules (shared with P3 — see config/confidence.yaml)
COUNT_AS_SUCCESS = CONFIDENCE_CONFIG["count_as_success"]
COUNT_AS_ATTEMPT = CONFIDENCE_CONFIG["count_as_attempt"]
MIN_COHORT_SIZE = CONFIDENCE_CONFIG["min_cohort_size"]
REQUIRE_SAME_RUNBOOK = CONFIDENCE_CONFIG.get("require_same_runbook", True)
PAST_FIX_SUCCESS_NEUTRAL = SIGNALS_CFG["past_fix_success"].get("neutral_value", 0.5)

# Reranker config (cross-encoder)
RERANKER_CFG = CONFIG.get("reranker", {})
RERANKER_ENABLED = RERANKER_CFG.get("enabled", False)
RERANKER_MODEL = RERANKER_CFG.get("model", "cross-encoder/ms-marco-MiniLM-L-2-v2")
RERANKER_TOP_N = RERANKER_CFG.get("top_n", 25)


def candidate_count_for(top_k: int) -> int:
    """Use a wider recall pool than the final result count."""
    return max(MIN_CANDIDATE_COUNT, top_k * CANDIDATE_MULT)


def tokenize_for_match(text: str) -> list[str]:
    """Tokenize query/content for exact-match features without substring false positives."""
    return re.findall(r"[a-z0-9\-]+", text.lower())


# --- Multi-Signal Scorer (config-driven) ---
class MultiSignalScorer(BaseNodePostprocessor):
    """Combine the deck's 4 signals (+ section_relevance, auxiliary) into an
    explainable score. RRF is deliberately excluded — see module docstring."""

    # Structured alert facts from the alert path, bypassing query-text
    # detection entirely. None on the manual/CLI query path, where no
    # structured alert exists and detection falls back to query text.
    alert_context: Optional[AlertContext] = None

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

        bm25_idf = get_bm25().idf
        idf_total = sum(bm25_idf.get(w, 1.0) for w in query_words) if query_words else 1.0

        # An alert always wants a corrective action — this shouldn't depend on
        # keyword-sniffing rendered text that was designed for manual CLI
        # queries ("how do I fix..."). alert_to_query()'s rendered sentence
        # ("...what corrective action should be taken?") shares no vocabulary
        # with ACTION_KEYWORDS, so is_action_query was always False on the
        # alert path — meaning section_relevance (the only per-section signal)
        # never favored resolution/mitigation sections, and a card could show
        # a confident band with recommended_action=None simply because no
        # action section happened to tie-break into the top-K. Same pattern as
        # component_match/exact_error_match: bypass text detection when a
        # structured alert exists.
        if self.alert_context is not None:
            is_action_query = True
            is_info_query = False
        else:
            is_action_query = bool(query_words & ACTION_KEYWORDS)
            is_info_query = bool(query_words & INFO_KEYWORDS)

        # Which service this query concerns — prefer the structured field from
        # the alert. Text-detection fallback only for manual/CLI queries with
        # no structured alert behind them (see AlertContext's docstring for why
        # this distinction matters).
        if self.alert_context is not None:
            query_service = self.alert_context.service
        else:
            query_service = None
            for svc in KNOWN_SERVICES_ORDERED:
                parts = [p for p in svc.split("-") if p not in ("service", "gateway", "general", "all")]
                if any(p in query_words for p in parts):
                    query_service = svc
                    break

        has_error_family = bool(
            self.alert_context and self.alert_context.error_family
            and self.alert_context.error_family != "unknown"
        )

        # Cohort lookups are cached per candidate_runbook for this request —
        # many candidates (all chunks of the same incident/runbook) share one
        # runbook id, and the cohort for a given (error_family, runbook) pair
        # never changes within a single request.
        cohort_cache: dict[str, dict] = {}

        def get_cohort(candidate_runbook: str) -> dict:
            if candidate_runbook not in cohort_cache:
                cohort_cache[candidate_runbook] = cohort_counts(
                    self.alert_context.error_family,
                    count_as_success=COUNT_AS_SUCCESS,
                    count_as_attempt=COUNT_AS_ATTEMPT,
                    resolution_runbook=candidate_runbook if REQUIRE_SAME_RUNBOOK else None,
                )
            return cohort_cache[candidate_runbook]

        for nws in nodes:
            text_lower = nws.node.get_content().lower()
            metadata = nws.node.metadata or {}
            section_name = metadata.get("section_name", "")
            doc_type = metadata.get("doc_type", "")
            node_service = metadata.get("service", "")
            doc_error_family = metadata.get("error_family")
            retrieval = dict(metadata.get("_retrieval") or {})

            # Retrieval features kept for audit only — NOT part of `combined`.
            semantic_score = nws.score or 0
            rrf_score = retrieval.get("rrf_score")
            if rrf_score is None:
                rrf_score = semantic_score

            # --- Signal A: exact_error_match ---
            # Structured error_family match (only incidents carry this metadata
            # today) is the strongest possible signal — a real match short-
            # circuits to 1.0. Otherwise fall back to IDF-weighted text overlap
            # (covers runbooks, which have no error_family of their own, and
            # the manual-query path).
            family_matched = bool(
                has_error_family and doc_error_family
                and doc_error_family == self.alert_context.error_family
            )
            if query_lower in text_lower:
                text_exact_score = 1.0
            else:
                text_words = set(tokenize_for_match(text_lower))
                weighted_hits = sum(bm25_idf.get(w, 1.0) for w in query_words if w in text_words)
                text_exact_score = (weighted_hits / idf_total) if idf_total > 0 else 0.0
            exact_error_match_score = 1.0 if family_matched else text_exact_score

            # --- Signal B: component_match ---
            # Alert path: direct structured equality (both sides are the same
            # canonical service slug — no substring/fuzzy matching needed).
            # Manual-query fallback: text-detected query_service, where partial
            # credit for a hyphen-part overlap still makes sense.
            if self.alert_context is not None:
                component_match_score = 1.0 if (node_service and query_service == node_service) else 0.0
            else:
                component_match_score = 0.0
                if query_service:
                    if query_service == node_service:
                        component_match_score = 1.0
                    elif any(p in node_service for p in query_service.split("-") if p not in ("service", "gateway")):
                        component_match_score = 0.7

            # --- Signal C: source_quality ---
            source_quality_score = SOURCE_QUALITY_TIERS.get(doc_type, 0.1)

            # --- Signal D: past_fix_success ---
            candidate_runbook = None
            if doc_type == "incident":
                candidate_runbook = metadata.get("resolution_runbook")
            elif doc_type == "runbook":
                candidate_runbook = metadata.get("id")

            past_fix_success_score = PAST_FIX_SUCCESS_NEUTRAL
            past_fix_cohort = None
            if has_error_family and candidate_runbook:
                past_fix_cohort = get_cohort(candidate_runbook)
                if past_fix_cohort["prior_total_n"] >= MIN_COHORT_SIZE:
                    past_fix_success_score = (
                        past_fix_cohort["prior_success_n"] / past_fix_cohort["prior_total_n"]
                    )
                # else: stays at neutral_value — cohort too small to judge, not
                # penalized and not rewarded (config/confidence.yaml's
                # min_cohort_size).

            # --- Signal E: section_relevance (auxiliary) ---
            section_relevance_score = 0.0
            if is_action_query:
                if section_name in ACTION_SECTIONS:
                    section_relevance_score = 1.0
                elif doc_type == "runbook":
                    section_relevance_score = 0.8
            elif is_info_query:
                if section_name in INFO_SECTIONS:
                    section_relevance_score = 1.0

            signal_scores = {
                "exact_error_match": exact_error_match_score,
                "component_match": component_match_score,
                "source_quality": source_quality_score,
                "past_fix_success": past_fix_success_score,
                "section_relevance": section_relevance_score,
            }
            combined = sum(
                SIGNALS_CFG[name]["weight"] * score
                for name, score in signal_scores.items()
                if SIGNALS_CFG[name].get("enabled", True)
            )

            penalty = 0.0
            if section_name in LOW_VALUE_SECTIONS:
                penalty = PENALTY_LOW_VALUE
                combined -= penalty

            nws.score = max(combined, 0.0)

            if ATTACH_EXPLANATIONS:
                metadata["_score_explain"] = {
                    "final_score": round(nws.score or 0.0, 6),
                    "weights": {name: cfg["weight"] for name, cfg in SIGNALS_CFG.items()},
                    "enabled": {name: cfg.get("enabled", True) for name, cfg in SIGNALS_CFG.items()},
                    "retrieval": {
                        "rrf_score": round(float(rrf_score or 0.0), 6),
                        "rrf_k": retrieval.get("rrf_k"),
                        "rrf_normalized": retrieval.get("rrf_normalized"),
                        "dense_rank": retrieval.get("dense_rank"),
                        "dense_score": retrieval.get("dense_score"),
                        "bm25_rank": retrieval.get("bm25_rank"),
                        "bm25_score": retrieval.get("bm25_score"),
                        "note": "recall-stage only — not part of `combined`",
                    },
                    "signals": {k: round(v, 6) for k, v in signal_scores.items()},
                    "penalties": {
                        "low_value_section": round(penalty, 6),
                    },
                    "context": {
                        "section_name": section_name,
                        "doc_type": doc_type,
                        "query_service": query_service,
                        "node_service": node_service,
                        "family_matched": family_matched,
                        "candidate_runbook": candidate_runbook,
                        "past_fix_cohort": past_fix_cohort,
                    },
                }
                nws.node.metadata = metadata

            if EXPLANATIONS_ENABLED:
                metadata["why_matched"] = _compose_why_matched(
                    family_matched=family_matched,
                    exact_error_match_score=exact_error_match_score,
                    text_exact_score=text_exact_score,
                    query_words=query_words,
                    text_lower=text_lower,
                    bm25_idf=bm25_idf,
                    component_match_score=component_match_score,
                    node_service=node_service,
                    doc_type=doc_type,
                    past_fix_success_fired=(past_fix_cohort is not None and past_fix_cohort["prior_total_n"] >= MIN_COHORT_SIZE),
                    past_fix_cohort=past_fix_cohort,
                    has_error_family=has_error_family,
                    section_relevance_score=section_relevance_score,
                    section_name=section_name,
                    error_family=self.alert_context.error_family if self.alert_context else None,
                )
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


def _compose_why_matched(
    *, family_matched, exact_error_match_score, text_exact_score, query_words, text_lower,
    bm25_idf, component_match_score, node_service, doc_type, past_fix_success_fired,
    past_fix_cohort, has_error_family, section_relevance_score, section_name, error_family,
) -> str:
    """Plain-language 'why this matched' (R7) — composed ONLY from signals that
    actually fired for THIS candidate. Never emits a phrase for a signal that
    didn't contribute, so it can't claim a match that didn't happen."""
    parts = []

    if family_matched:
        parts.append(EXPLANATION_TEMPLATES["exact_error_match_family"].format(error_family=error_family))
    elif text_exact_score > 0.3:
        text_words = set(tokenize_for_match(text_lower))
        matched = sorted(query_words & text_words, key=lambda w: -bm25_idf.get(w, 0.0))[:5]
        if matched:
            parts.append(EXPLANATION_TEMPLATES["exact_error_match_text"].format(matched_terms=", ".join(matched)))

    if component_match_score >= 1.0 and node_service:
        parts.append(EXPLANATION_TEMPLATES["component_match"].format(component=node_service))

    if doc_type in ("runbook", "incident"):
        parts.append(EXPLANATION_TEMPLATES["source_quality"].format(doc_type=doc_type))

    if past_fix_success_fired and past_fix_cohort:
        parts.append(EXPLANATION_TEMPLATES["past_fix_success"].format(
            prior_success_n=past_fix_cohort["prior_success_n"],
            prior_total_n=past_fix_cohort["prior_total_n"],
        ))
    elif has_error_family and past_fix_cohort and past_fix_cohort["prior_total_n"] < MIN_COHORT_SIZE:
        parts.append(EXPLANATION_TEMPLATES["past_fix_success_neutral"].format(
            prior_total_n=past_fix_cohort["prior_total_n"],
        ))

    if section_relevance_score >= 1.0:
        parts.append(EXPLANATION_TEMPLATES["section_relevance"].format(section_name=section_name))

    if not parts:
        parts.append(EXPLANATION_TEMPLATES.get("no_signals_fired", "Retrieved by semantic similarity"))

    return "; ".join(parts)


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
    """LlamaIndex retriever wrapper that returns RRF-fused hybrid candidates
    (recall stage), optionally narrowed by a cross-encoder, then ranked by the
    deterministic multi-signal scorer (ranking stage)."""

    def __init__(
        self,
        vector_retriever: VectorIndexRetriever,
        candidate_count: int,
        top_k: int,
        alert_context: Optional[AlertContext] = None,
    ):
        super().__init__()
        self.vector_retriever = vector_retriever
        self.candidate_count = candidate_count
        self.top_k = top_k
        self.scorer = MultiSignalScorer(alert_context=alert_context)

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        pool = hybrid_candidates(
            query_bundle.query_str,
            self.vector_retriever,
            candidate_count=self.candidate_count,
        )

        # Cross-encoder: candidate-pool narrowing only, never the final ranking
        # step (see config/scoring.yaml's reranker comment / the P0 architecture
        # review) — it runs BEFORE the explainable scorer, not after.
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
    error_family: Optional[str] = None,
) -> Optional[MetadataFilters]:
    """
    Build LlamaIndex MetadataFilters from explicit overrides.

    service / error_family strictness is config-driven (retrieval_filters in
    scoring.yaml): 'strict' applies a real ChromaDB WHERE-equality filter
    (narrows the DENSE half of the candidate pool only — BM25 always scans the
    full corpus, same asymmetry the original service filter already had);
    'soft' does not filter at all, leaving the matching scoring signal
    (component_match / exact_error_match) to reward matches instead of
    excluding non-matches from the pool. error_family defaults to soft because
    enrichment coverage is incomplete (see config/scoring.yaml's comment).
    """
    filters = []
    if doc_type:
        filters.append(MetadataFilter(key="doc_type", value=doc_type, operator=FilterOperator.EQ))
    if service and SERVICE_FILTER_MODE == "strict":
        filters.append(MetadataFilter(key="service", value=service.lower(), operator=FilterOperator.EQ))
    if severity:
        filters.append(MetadataFilter(key="severity", value=severity.upper(), operator=FilterOperator.EQ))
    if error_family and error_family != "unknown" and ERROR_FAMILY_FILTER_MODE == "strict":
        filters.append(MetadataFilter(key="error_family", value=error_family, operator=FilterOperator.EQ))
    if filters:
        return MetadataFilters(filters=filters, condition=FilterCondition.AND)
    return None


# --- Retrieval-only path (no LLM) ---
def retrieve_only(
    query: str,
    top_k: int = FINAL_TOP_K_DEFAULT,
    service: Optional[str] = None,
    alert_context: Optional[AlertContext] = None,
) -> list[NodeWithScore]:
    """Run retrieval + scoring — hybrid candidates, optional cross-encoder
    narrowing, deterministic multi-signal scoring. No LLM call. Used directly
    by src/recommendation.py's build_recommendation_card(), and by
    tests/evaluate.py / tests/evaluate_alert_path.py to measure Recall@3/MRR
    without paying for an LLM call per query."""
    from src.retrieval import is_id_lookup, id_lookup

    if is_id_lookup(query):
        return id_lookup(query, top_k=top_k)

    error_family = alert_context.error_family if alert_context else None
    index = load_index()
    metadata_filters = build_metadata_filters(service=service, error_family=error_family)
    retriever = VectorIndexRetriever(
        index=index,
        similarity_top_k=candidate_count_for(top_k),
        filters=metadata_filters,
    )
    hybrid = HybridRetriever(
        retriever,
        candidate_count=candidate_count_for(top_k),
        top_k=top_k,
        alert_context=alert_context,
    )
    return hybrid._retrieve(QueryBundle(query_str=query))
