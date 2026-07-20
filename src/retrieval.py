"""
Retrieval layer: config loading, ID routing, BM25 keyword search,
hybrid fusion (RRF), and multi-signal scoring.

Separates retrieval concerns from the CLI/server presentation layer.
"""

import re
import math
from pathlib import Path
from functools import lru_cache
from typing import Optional

import yaml

from src.indexer import get_chroma_collection

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "scoring.yaml"


# --- Config loading (3.2) ---
def load_scoring_config() -> dict:
    """Load scoring config from YAML. Falls back to defaults if missing."""
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    # ponytail: minimal fallback if config file is missing
    return {
        "weights": {"rrf": 0.55, "exact_match": 0.13, "metadata_match": 0.13, "section_relevance": 0.09, "doc_type_priority": 0.10},
        "penalties": {"low_value_sections": ["links", "revision-history"], "penalty_amount": 0.2},
        "thresholds": {"id_lookup_regex": r"^[A-Z]{2,5}-\d{1,4}$", "candidate_multiplier": 8, "min_candidate_count": 50, "rrf_k": 60},
        "scoring": {"normalize_rrf": True, "minmax_normalize_final": False, "attach_explanations": True},
        "intent_keywords": {"action": ["fix", "how"], "info": ["what", "why"]},
        "action_sections": ["resolution", "triage"],
        "info_sections": ["summary", "timeline"],
        "known_services": ["payment-gateway", "auth-service"],
        "doc_type_priority": {"runbook": 1.0, "incident": 0.75, "system": 0.5, "governance": 0.4, "vendor-note": 0.2, "template": 0.0, "unknown": 0.1},
    }


CONFIG = load_scoring_config()
_ID_REGEX = re.compile(CONFIG["thresholds"]["id_lookup_regex"], re.IGNORECASE)
RRF_K = CONFIG["thresholds"].get("rrf_k", 60)
NORMALIZE_RRF = CONFIG.get("scoring", {}).get("normalize_rrf", True)
_EXPLAIN_KEYS = ("_retrieval", "_score_explain")


# --- ID routing (2.1) ---
def is_id_lookup(query: str) -> bool:
    """True if the query is just a document ID like INC-003, RB-001."""
    return bool(_ID_REGEX.match(query.strip()))


def id_lookup(doc_id: str, top_k: int = 8) -> list:
    """
    Direct metadata lookup — no embedding, no vector search.
    Returns NodeWithScore objects for all sections of the matching doc.
    """
    from llama_index.core.schema import TextNode, NodeWithScore

    collection = get_chroma_collection()
    doc_id = doc_id.strip().upper()

    # ChromaDB metadata filter on the 'id' field
    results = collection.get(where={"id": doc_id}, include=["documents", "metadatas"])

    nodes = []
    ids = results.get("ids") or []
    for i, node_id in enumerate(ids):
        metadata = results["metadatas"][i] if results.get("metadatas") else {}
        text = results["documents"][i] if results.get("documents") else ""
        node = TextNode(text=text, metadata=metadata, id_=node_id)
        nodes.append(NodeWithScore(node=node, score=1.0))  # exact match = perfect score

    return nodes[:top_k]


# --- BM25 keyword index (2.2) ---
class BM25Index:
    """
    Minimal in-memory BM25 over ALL nodes in ChromaDB.
    Built once, cached. Searches the full corpus (not just dense candidates) —
    this is what fixes the "exact match only sees top-k candidates" flaw.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.node_ids: list[str] = []
        self.texts: list[str] = []
        self.metadatas: list[dict] = []
        self.tokenized: list[list[str]] = []
        self.doc_freq: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.avg_len: float = 0.0
        self._built = False

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-z0-9\-]+", text.lower())

    def build(self):
        """Load all nodes from ChromaDB and compute BM25 statistics."""
        collection = get_chroma_collection()
        total = collection.count()
        # ponytail: loads full corpus into memory. Fine for <100K nodes.
        # Upgrade path: Elasticsearch/OpenSearch inverted index at scale.
        results = collection.get(limit=max(total, 1), include=["documents", "metadatas"])

        self.node_ids = results.get("ids") or []
        self.texts = results.get("documents") or []
        self.metadatas = results.get("metadatas") or []
        self.tokenized = [self._tokenize(t) for t in self.texts]

        # Document frequency per term
        self.doc_freq = {}
        for tokens in self.tokenized:
            for term in set(tokens):
                self.doc_freq[term] = self.doc_freq.get(term, 0) + 1

        n = len(self.tokenized)
        self.avg_len = sum(len(t) for t in self.tokenized) / n if n else 0.0

        # IDF (BM25 variant)
        self.idf = {}
        for term, df in self.doc_freq.items():
            self.idf[term] = math.log(1 + (n - df + 0.5) / (df + 0.5))

        self._built = True

    def search(self, query: str, top_k: int = 16) -> list[tuple[str, float, str, dict]]:
        """Return [(node_id, score, text, metadata)] ranked by BM25."""
        if not self._built:
            self.build()

        q_terms = self._tokenize(query)
        scores = []
        for idx, tokens in enumerate(self.tokenized):
            if not tokens:
                continue
            doc_len = len(tokens)
            score = 0.0
            tf = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            for term in q_terms:
                if term not in tf:
                    continue
                idf = self.idf.get(term, 0.0)
                freq = tf[term]
                denom = freq + self.k1 * (1 - self.b + self.b * doc_len / self.avg_len)
                score += idf * (freq * (self.k1 + 1)) / denom
            if score > 0:
                scores.append((idx, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        out = []
        for idx, score in scores[:top_k]:
            out.append((self.node_ids[idx], score, self.texts[idx], self.metadatas[idx]))
        return out


# Module-level cached BM25 index (built on first use)
_bm25: Optional[BM25Index] = None


def get_bm25() -> BM25Index:
    global _bm25
    if _bm25 is None:
        _bm25 = BM25Index()
        _bm25.build()
    return _bm25


def reset_bm25():
    """Call after re-ingestion to rebuild the BM25 index."""
    global _bm25
    _bm25 = None


def _rrf_score(dense_rank: Optional[int], bm25_rank: Optional[int]) -> float:
    """Compute reciprocal rank fusion from available source ranks."""
    score = 0.0
    if dense_rank is not None:
        score += 1.0 / (RRF_K + dense_rank)
    if bm25_rank is not None:
        score += 1.0 / (RRF_K + bm25_rank)
    if not NORMALIZE_RRF:
        return score
    max_score = 2.0 / (RRF_K + 1)
    return score / max_score if max_score else score


def _hide_score_metadata_from_llm(node) -> None:
    """Keep debug scoring metadata available to APIs without adding it to prompt context."""
    for attr in ("excluded_llm_metadata_keys", "excluded_embed_metadata_keys"):
        keys = list(getattr(node, attr, []) or [])
        for key in _EXPLAIN_KEYS:
            if key not in keys:
                keys.append(key)
        if hasattr(node, attr):
            setattr(node, attr, keys)


# --- Hybrid candidate generation (2.2) ---
def hybrid_candidates(query: str, vector_retriever, candidate_count: int) -> list:
    """
    Build a candidate pool = union(dense top-N, BM25 top-N).

    Dense retrieval finds semantically similar nodes (cosine score preserved).
    BM25 finds exact-term matches the dense retriever may have missed
    (IDs, error strings, rare terms) — these enter the pool with semantic score 0
    but will earn a high exact_match signal in the scorer.

    This fixes the core flaw: exact matches now enter the candidate set even
    when dense retrieval ranks them outside its top-N.
    """
    from llama_index.core.schema import TextNode, NodeWithScore

    # Dense candidates (cosine score and rank are kept as retrieval features)
    dense_nodes = vector_retriever.retrieve(query)
    by_id = {}
    for rank, nws in enumerate(dense_nodes, 1):
        node_id = nws.node.node_id
        metadata = dict(nws.node.metadata or {})
        metadata["_retrieval"] = {
            "dense_rank": rank,
            "dense_score": nws.score or 0.0,
            "bm25_rank": None,
            "bm25_score": None,
        }
        nws.node.metadata = metadata
        _hide_score_metadata_from_llm(nws.node)
        by_id[node_id] = nws

    # BM25 candidates over the FULL corpus
    bm25_hits = get_bm25().search(query, top_k=candidate_count)
    for rank, (node_id, bm25_score, text, meta) in enumerate(bm25_hits, 1):
        if node_id in by_id:
            metadata = dict(by_id[node_id].node.metadata or {})
            retrieval = dict(metadata.get("_retrieval") or {})
            retrieval["bm25_rank"] = rank
            retrieval["bm25_score"] = bm25_score
            metadata["_retrieval"] = retrieval
            by_id[node_id].node.metadata = metadata
        else:
            metadata = dict(meta or {})
            metadata["_retrieval"] = {
                "dense_rank": None,
                "dense_score": None,
                "bm25_rank": rank,
                "bm25_score": bm25_score,
            }
            node = TextNode(text=text, metadata=meta, id_=node_id)
            node.metadata = metadata
            _hide_score_metadata_from_llm(node)
            # semantic score unknown for BM25-only nodes; RRF/BM25 features will carry them
            by_id[node_id] = NodeWithScore(node=node, score=0.0)

    for nws in by_id.values():
        metadata = dict(nws.node.metadata or {})
        retrieval = dict(metadata.get("_retrieval") or {})
        dense_rank = retrieval.get("dense_rank")
        bm25_rank = retrieval.get("bm25_rank")
        retrieval["rrf_score"] = _rrf_score(dense_rank, bm25_rank)
        retrieval["rrf_k"] = RRF_K
        retrieval["rrf_normalized"] = NORMALIZE_RRF
        metadata["_retrieval"] = retrieval
        nws.node.metadata = metadata

    pool = list(by_id.values())

    return pool
