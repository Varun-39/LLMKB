"""
Retrieval evaluation harness.

Runs every query in validation_queries.json through retrieve_only(), then measures:
  - Recall@3   : was an expected doc in the top 3 results?
  - MRR        : 1/rank of the first expected doc (0 if not found)

Run:
    python -m tests.evaluate
    python -m tests.evaluate --top-k 5

Use this BEFORE and AFTER any scoring change to catch regressions.
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import init_llama_index_settings
from src.query import retrieve_only

VALIDATION_FILE = Path(__file__).resolve().parent / "validation_queries.json"


def doc_ids_from_nodes(nodes) -> list[str]:
    """Extract the ordered list of doc IDs from retrieved nodes (dedup, keep order)."""
    seen = set()
    ordered = []
    for n in nodes:
        doc_id = n.node.metadata.get("id", "?")
        if doc_id not in seen:
            ordered.append(doc_id)
            seen.add(doc_id)
    return ordered


def evaluate(top_k: int = 8) -> dict:
    init_llama_index_settings()

    with open(VALIDATION_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)

    results = []
    recall_hits = 0
    mrr_sum = 0.0

    for case in cases:
        query = case["query"]
        expected = set(case["expected"])

        nodes = retrieve_only(query, top_k=top_k)
        retrieved_ids = doc_ids_from_nodes(nodes)

        # Recall@3: any expected doc in top 3 distinct docs?
        top3 = retrieved_ids[:3]
        recall_hit = bool(expected & set(top3))
        if recall_hit:
            recall_hits += 1

        # MRR: reciprocal rank of first expected doc
        rr = 0.0
        for rank, doc_id in enumerate(retrieved_ids, 1):
            if doc_id in expected:
                rr = 1.0 / rank
                break
        mrr_sum += rr

        results.append({
            "query": query,
            "expected": list(expected),
            "top3": top3,
            "recall@3": recall_hit,
            "rr": round(rr, 3),
        })

    n = len(cases)
    return {
        "total": n,
        "recall@3": round(recall_hits / n, 3),
        "mrr": round(mrr_sum / n, 3),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--verbose", action="store_true", help="Show per-query results")
    args = parser.parse_args()

    report = evaluate(top_k=args.top_k)

    print("=" * 60)
    print(f"  Retrieval Evaluation ({report['total']} queries, top_k={args.top_k})")
    print("=" * 60)
    print(f"  Recall@3: {report['recall@3']:.1%}  (expected doc in top 3)")
    print(f"  MRR:      {report['mrr']:.3f}  (mean reciprocal rank)")
    print("=" * 60)

    if args.verbose:
        print("\nPer-query:")
        for r in report["results"]:
            mark = "PASS" if r["recall@3"] else "FAIL"
            print(f"  [{mark}] rr={r['rr']:.2f} | {r['query'][:45]:45} | top3={r['top3']}")

    # Always show failures
    failures = [r for r in report["results"] if not r["recall@3"]]
    if failures:
        print(f"\n{len(failures)} FAILURES (expected doc not in top 3):")
        for r in failures:
            print(f"  - \"{r['query']}\" expected {r['expected']}, got {r['top3']}")


if __name__ == "__main__":
    main()
