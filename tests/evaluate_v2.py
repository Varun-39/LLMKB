"""
Comprehensive retrieval & generation evaluation harness (v2).

Extends the original evaluate.py with LlamaIndex's evaluation modules:
  - Retrieval:    Hit Rate, MRR, NDCG, Precision, Recall
  - Generation:   Faithfulness (groundedness), Relevancy (answer quality)
  - Synthetic QA: Auto-generate evaluation questions from your corpus

Usage:
    python -m tests.evaluate_v2                          # retrieval only
    python -m tests.evaluate_v2 --with-generation        # + faithfulness & relevancy
    python -m tests.evaluate_v2 --generate-synthetic 5   # gen N questions per chunk
    python -m tests.evaluate_v2 --verbose                # per-query results
    python -m tests.evaluate_v2 --top-k 5                # override retrieval depth

Use BEFORE and AFTER any scoring/retrieval change to catch regressions.
"""

import sys
import json
import time
import argparse
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import init_llama_index_settings
from src.query import retrieve_only, build_query_engine
from src.retrieval import is_id_lookup

console = Console()

VALIDATION_FILE = Path(__file__).resolve().parent / "validation_queries.json"
RESULTS_DIR = Path(__file__).resolve().parent / "eval_results"


# ─── Retrieval Metrics ────────────────────────────────────────────────────

def dcg_at_k(relevances: list[float], k: int) -> float:
    """Discounted cumulative gain at rank k."""
    import math
    score = 0.0
    for i, rel in enumerate(relevances[:k]):
        score += rel / math.log2(i + 2)  # i+2 because rank is 1-indexed
    return score


def ndcg_at_k(relevances: list[float], k: int) -> float:
    """Normalized DCG at rank k."""
    ideal = sorted(relevances, reverse=True)
    ideal_dcg = dcg_at_k(ideal, k)
    if ideal_dcg == 0:
        return 0.0
    return dcg_at_k(relevances, k) / ideal_dcg


def doc_ids_from_nodes(nodes) -> list[str]:
    """Extract ordered list of doc IDs from retrieved nodes (dedup, keep order)."""
    seen = set()
    ordered = []
    for n in nodes:
        doc_id = n.node.metadata.get("id", "?")
        if doc_id not in seen:
            ordered.append(doc_id)
            seen.add(doc_id)
    return ordered


def evaluate_retrieval(top_k: int = 8, eval_at: int = 3) -> dict:
    """
    Run retrieval evaluation over validation_queries.json.

    Metrics computed:
      - Hit Rate @eval_at: fraction of queries where any expected doc appears in top-eval_at
      - MRR: Mean Reciprocal Rank of first expected doc
      - NDCG @eval_at: Normalized Discounted Cumulative Gain
      - Precision @eval_at: fraction of top-eval_at docs that are expected
      - Recall @eval_at: fraction of expected docs found in top-eval_at
    """
    with open(VALIDATION_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)

    results = []
    hit_count = 0
    mrr_sum = 0.0
    ndcg_sum = 0.0
    precision_sum = 0.0
    recall_sum = 0.0
    total_latency = 0.0

    for case in cases:
        query = case["query"]
        expected = set(case["expected"])

        t0 = time.perf_counter()
        nodes = retrieve_only(query, top_k=top_k)
        latency = time.perf_counter() - t0
        total_latency += latency

        retrieved_ids = doc_ids_from_nodes(nodes)

        # Hit Rate @eval_at
        top_eval = retrieved_ids[:eval_at]
        hit = bool(expected & set(top_eval))
        if hit:
            hit_count += 1

        # MRR
        rr = 0.0
        for rank, doc_id in enumerate(retrieved_ids, 1):
            if doc_id in expected:
                rr = 1.0 / rank
                break
        mrr_sum += rr

        # NDCG @eval_at
        relevances = [1.0 if doc_id in expected else 0.0 for doc_id in retrieved_ids]
        ndcg = ndcg_at_k(relevances, eval_at)
        ndcg_sum += ndcg

        # Precision @eval_at
        relevant_in_top = sum(1 for d in top_eval if d in expected)
        precision = relevant_in_top / eval_at if eval_at > 0 else 0.0
        precision_sum += precision

        # Recall @eval_at
        recall = relevant_in_top / len(expected) if expected else 0.0
        recall_sum += recall

        results.append({
            "query": query,
            "expected": list(expected),
            "top_k_ids": top_eval,
            "hit": hit,
            "rr": round(rr, 4),
            "ndcg": round(ndcg, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "latency_s": round(latency, 3),
        })

    n = len(cases)
    return {
        "total_queries": n,
        "eval_at": eval_at,
        "top_k": top_k,
        "metrics": {
            "hit_rate": round(hit_count / n, 4) if n else 0,
            "mrr": round(mrr_sum / n, 4) if n else 0,
            "ndcg": round(ndcg_sum / n, 4) if n else 0,
            "precision": round(precision_sum / n, 4) if n else 0,
            "recall": round(recall_sum / n, 4) if n else 0,
        },
        "avg_latency_s": round(total_latency / n, 3) if n else 0,
        "results": results,
    }


# ─── Generation Quality Metrics ──────────────────────────────────────────

def evaluate_generation(top_k: int = 8, max_queries: Optional[int] = None) -> dict:
    """
    Run faithfulness and relevancy evaluation on generated answers.

    Uses LLM-as-a-judge to assess:
      - Faithfulness: Is the answer grounded in the retrieved context? (0 or 1)
      - Relevancy: Is the answer relevant to the query? (0 or 1)

    Note: This is slow (~10-30s per query due to Ollama eval LLM calls).
    Use --max-gen-queries to limit the number of queries evaluated.
    """
    from llama_index.core.evaluation import FaithfulnessEvaluator, RelevancyEvaluator

    faithfulness_eval = FaithfulnessEvaluator()
    relevancy_eval = RelevancyEvaluator()

    with open(VALIDATION_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)

    # Skip ID lookups — they don't generate answers
    gen_cases = [c for c in cases if not is_id_lookup(c["query"])]
    if max_queries:
        gen_cases = gen_cases[:max_queries]

    results = []
    faith_pass = 0
    relev_pass = 0

    for i, case in enumerate(gen_cases, 1):
        query = case["query"]
        console.print(f"  [{i}/{len(gen_cases)}] Evaluating: {query[:50]}...", style="dim")

        try:
            qe = build_query_engine(top_k=top_k)
            response = qe.query(query)

            # Faithfulness: is the response grounded in the context?
            faith_result = faithfulness_eval.evaluate_response(response=response)
            faith_score = 1.0 if faith_result.passing else 0.0

            # Relevancy: is the response relevant to the query?
            relev_result = relevancy_eval.evaluate_response(
                query=query, response=response
            )
            relev_score = 1.0 if relev_result.passing else 0.0

            if faith_score > 0:
                faith_pass += 1
            if relev_score > 0:
                relev_pass += 1

            results.append({
                "query": query,
                "faithfulness": faith_score,
                "relevancy": relev_score,
                "answer_preview": str(response)[:200],
                "faith_feedback": str(faith_result.feedback)[:200] if faith_result.feedback else None,
                "relev_feedback": str(relev_result.feedback)[:200] if relev_result.feedback else None,
            })
        except Exception as e:
            console.print(f"    [red]ERROR: {e}[/]")
            results.append({
                "query": query,
                "faithfulness": 0.0,
                "relevancy": 0.0,
                "error": str(e),
            })

    n = len(gen_cases)
    return {
        "total_queries": n,
        "metrics": {
            "faithfulness_rate": round(faith_pass / n, 4) if n else 0,
            "relevancy_rate": round(relev_pass / n, 4) if n else 0,
        },
        "results": results,
    }


# ─── Synthetic Question Generation ───────────────────────────────────────

def generate_synthetic_questions(num_per_chunk: int = 2, max_chunks: int = 20) -> list[dict]:
    """
    Auto-generate evaluation questions from your indexed corpus.

    Uses LlamaIndex to create questions that a chunk can answer,
    providing ground-truth (chunk_id, doc_id) for each.

    Returns list of {"query": ..., "expected": [...], "source_chunk": ...}
    """
    from src.indexer import get_chroma_collection
    from llama_index.core import Settings

    console.print("[bold blue]Generating synthetic evaluation questions...[/]")

    collection = get_chroma_collection()
    total = min(collection.count(), max_chunks)
    results = collection.get(limit=total, include=["documents", "metadatas"])

    llm = Settings.llm
    synthetic_cases = []

    for i in range(min(len(results["ids"]), max_chunks)):
        text = results["documents"][i]
        metadata = results["metadatas"][i] if results.get("metadatas") else {}
        doc_id = metadata.get("id", "?")
        section = metadata.get("section_name", "?")

        # Skip low-value sections
        if section in ("links", "revision-history", "preamble"):
            continue

        # Use the LLM to generate questions
        prompt = f"""Based on the following text from an SRE knowledge base, generate {num_per_chunk} specific questions that this text can answer.
Return only the questions, one per line, with no numbering or prefixes.

Text:
{text[:2000]}

Questions:"""

        try:
            response = llm.complete(prompt)
            questions = [q.strip() for q in str(response).strip().split("\n") if q.strip() and len(q.strip()) > 10]

            for q in questions[:num_per_chunk]:
                synthetic_cases.append({
                    "query": q,
                    "expected": [doc_id],
                    "source_chunk": f"{doc_id}::{section}",
                    "synthetic": True,
                })

            console.print(f"  [{i+1}/{total}] {doc_id}::{section} → {len(questions[:num_per_chunk])} questions")
        except Exception as e:
            console.print(f"  [{i+1}/{total}] {doc_id}::{section} → ERROR: {e}")

    return synthetic_cases


# ─── Display ──────────────────────────────────────────────────────────────

def display_retrieval_report(report: dict, verbose: bool = False) -> None:
    """Display retrieval metrics in rich tables."""
    m = report["metrics"]

    console.print()
    console.print(Panel(
        f"[bold]Retrieval Evaluation[/]\n"
        f"Queries: {report['total_queries']} | top_k: {report['top_k']} | eval@{report['eval_at']}",
        title="[bold cyan]AI Runbook Assistant — Evaluation Report[/]",
        border_style="cyan",
    ))

    table = Table(title="Retrieval Metrics", show_header=True)
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Score", style="green", width=12)
    table.add_column("Description", style="dim", width=45)

    table.add_row("Hit Rate", f"{m['hit_rate']:.1%}", f"Expected doc in top {report['eval_at']}")
    table.add_row("MRR", f"{m['mrr']:.4f}", "Mean Reciprocal Rank of first expected doc")
    table.add_row("NDCG", f"{m['ndcg']:.4f}", f"Normalized DCG @{report['eval_at']}")
    table.add_row("Precision", f"{m['precision']:.4f}", f"Relevant / retrieved @{report['eval_at']}")
    table.add_row("Recall", f"{m['recall']:.4f}", f"Relevant found / total relevant @{report['eval_at']}")
    table.add_row("Avg Latency", f"{report['avg_latency_s']:.3f}s", "Mean retrieval time per query")
    console.print(table)

    if verbose:
        detail_table = Table(title="Per-Query Results")
        detail_table.add_column("Status", width=5)
        detail_table.add_column("RR", width=6)
        detail_table.add_column("NDCG", width=6)
        detail_table.add_column("Query", width=40)
        detail_table.add_column("Top-3", width=30)

        for r in report["results"]:
            mark = "[green]PASS[/]" if r["hit"] else "[red]FAIL[/]"
            detail_table.add_row(
                mark,
                f"{r['rr']:.2f}",
                f"{r['ndcg']:.2f}",
                r["query"][:40],
                ", ".join(r["top_k_ids"][:3]),
            )
        console.print(detail_table)

    # Always show failures
    failures = [r for r in report["results"] if not r["hit"]]
    if failures:
        console.print(f"\n[bold red]{len(failures)} FAILURES[/] (expected doc not in top {report['eval_at']}):")
        for r in failures:
            console.print(f"  ✗ \"{r['query']}\" expected {r['expected']}, got {r['top_k_ids']}")


def display_generation_report(report: dict) -> None:
    """Display generation quality metrics."""
    m = report["metrics"]

    console.print()
    table = Table(title="Generation Quality Metrics", show_header=True)
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Score", style="green", width=12)
    table.add_column("Description", style="dim", width=45)

    table.add_row("Faithfulness", f"{m['faithfulness_rate']:.1%}", "Answer grounded in retrieved context")
    table.add_row("Relevancy", f"{m['relevancy_rate']:.1%}", "Answer relevant to the query")
    console.print(table)

    # Show failures
    gen_failures = [r for r in report["results"]
                    if r.get("faithfulness", 1) < 1 or r.get("relevancy", 1) < 1]
    if gen_failures:
        console.print(f"\n[bold yellow]{len(gen_failures)} Generation Issues:[/]")
        for r in gen_failures:
            issues = []
            if r.get("faithfulness", 1) < 1:
                issues.append("unfaithful")
            if r.get("relevancy", 1) < 1:
                issues.append("irrelevant")
            console.print(f"  ⚠ \"{r['query'][:50]}\" — {', '.join(issues)}")
            if r.get("faith_feedback"):
                console.print(f"    Faith: {r['faith_feedback'][:100]}", style="dim")
            if r.get("relev_feedback"):
                console.print(f"    Relev: {r['relev_feedback'][:100]}", style="dim")


# ─── Save Results ─────────────────────────────────────────────────────────

def save_results(report: dict, filename: str) -> None:
    """Save evaluation results to JSON for comparison over time."""
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = RESULTS_DIR / f"{filename}_{timestamp}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    console.print(f"\n[dim]Results saved to {filepath}[/]")


# ─── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI Runbook Assistant — Comprehensive Retrieval & Generation Evaluation (v2)"
    )
    parser.add_argument("--top-k", type=int, default=8, help="Retrieval depth")
    parser.add_argument("--eval-at", type=int, default=3, help="Evaluate metrics @k (default: 3)")
    parser.add_argument("--verbose", action="store_true", help="Show per-query results")
    parser.add_argument("--with-generation", action="store_true",
                        help="Also evaluate faithfulness and relevancy (slow)")
    parser.add_argument("--max-gen-queries", type=int, default=10,
                        help="Max queries for generation eval (default: 10)")
    parser.add_argument("--generate-synthetic", type=int, default=0,
                        help="Generate N synthetic questions per chunk and save to file")
    parser.add_argument("--save", action="store_true", help="Save results to JSON")
    args = parser.parse_args()

    init_llama_index_settings()

    # --- Synthetic question generation mode ---
    if args.generate_synthetic > 0:
        synthetic = generate_synthetic_questions(
            num_per_chunk=args.generate_synthetic, max_chunks=20
        )
        output_path = Path(__file__).resolve().parent / "synthetic_queries.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(synthetic, f, indent=2)
        console.print(f"\n[bold green]Generated {len(synthetic)} synthetic questions → {output_path}[/]")
        return

    # --- Retrieval evaluation ---
    console.print("\n[bold cyan]═══ Phase 1: Retrieval Evaluation ═══[/]\n")

    t0 = time.perf_counter()
    retrieval_report = evaluate_retrieval(top_k=args.top_k, eval_at=args.eval_at)
    retrieval_time = time.perf_counter() - t0

    display_retrieval_report(retrieval_report, verbose=args.verbose)
    console.print(f"\n[dim]Retrieval eval completed in {retrieval_time:.1f}s[/]")

    if args.save:
        save_results(retrieval_report, "retrieval")

    # --- Generation evaluation (optional, slow) ---
    if args.with_generation:
        console.print("\n[bold cyan]═══ Phase 2: Generation Quality Evaluation ═══[/]\n")
        console.print("[dim]This evaluates faithfulness and relevancy using LLM-as-judge.[/]")
        console.print(f"[dim]Evaluating up to {args.max_gen_queries} queries (use --max-gen-queries to change).[/]\n")

        gen_report = evaluate_generation(
            top_k=args.top_k, max_queries=args.max_gen_queries
        )
        display_generation_report(gen_report)

        if args.save:
            save_results(gen_report, "generation")

    # --- Summary ---
    console.print("\n" + "═" * 60)
    m = retrieval_report["metrics"]
    console.print(f"  [bold]Summary[/]: Hit Rate={m['hit_rate']:.1%}  MRR={m['mrr']:.4f}  "
                  f"NDCG={m['ndcg']:.4f}  Prec={m['precision']:.4f}  Rec={m['recall']:.4f}")
    console.print("═" * 60 + "\n")


if __name__ == "__main__":
    main()
