"""
Alert-path retrieval evaluation harness (Decision 2, pre-UI-closeout session).

evaluate.py measures the MANUAL-query path (free text, no AlertContext) — the
real /alert path is fingerprint -> AlertContext -> retrieval -> scoring, and
its past_fix_success signal only activates with a real AlertContext, which
evaluate.py's queries never provide. This script closes that blind spot: same
Recall@3/MRR metric, computed against tests/alert_validation_cases.json (real
SplunkAlert-shaped fixtures with a known-correct expected runbook), run through
the actual alert path.

Also reports the confidence band achieved per case (informational only, not
scored into Recall@3/MRR) — a rough, small-sample preview of the calibration
question J1's full replay harness answers properly later.

Run:
    python -m tests.evaluate_alert_path
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import init_llama_index_settings
from src.alerts import SplunkAlert, alert_to_query, build_alert_context
from src.fingerprint import compute_fingerprint
from src.query import retrieve_only, FINAL_TOP_K_DEFAULT
from src.confidence import compute_confidence
from src.recommendation import _find_recommended_runbook

FIXTURES_FILE = Path(__file__).resolve().parent / "alert_validation_cases.json"
SAMPLE_ALERTS_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_alerts"


def doc_ids_from_nodes(nodes) -> list[str]:
    seen = set()
    ordered = []
    for n in nodes:
        doc_id = n.node.metadata.get("id", "?")
        if doc_id not in seen:
            ordered.append(doc_id)
            seen.add(doc_id)
    return ordered


def evaluate(top_k: int = FINAL_TOP_K_DEFAULT) -> dict:
    init_llama_index_settings()

    with open(FIXTURES_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)

    results = []
    recall_hits = 0
    mrr_sum = 0.0

    for case in cases:
        raw = json.loads((SAMPLE_ALERTS_DIR / case["alert_file"]).read_text(encoding="utf-8"))
        alert = SplunkAlert.model_validate(raw)
        fp = compute_fingerprint(
            raw_text=alert.result.message, service=alert.result.service,
            environment=alert.result.environment, stack_trace=alert.result.stack_trace,
        )
        ctx = build_alert_context(alert, fp)
        query_text = alert_to_query(alert, fingerprint=fp)

        nodes = retrieve_only(query_text, top_k=top_k, service=alert.result.service, alert_context=ctx)
        retrieved_ids = doc_ids_from_nodes(nodes)
        expected = set(case["expected"])

        top3 = retrieved_ids[:3]
        recall_hit = bool(expected & set(top3))
        if recall_hit:
            recall_hits += 1

        rr = 0.0
        for rank, doc_id in enumerate(retrieved_ids, 1):
            if doc_id in expected:
                rr = 1.0 / rank
                break
        mrr_sum += rr

        recommended_runbook = _find_recommended_runbook(nodes)
        confidence = compute_confidence(ctx.error_family, recommended_runbook)

        results.append({
            "name": case["name"],
            "error_family": ctx.error_family,
            "expected": list(expected),
            "top3": top3,
            "recall@3": recall_hit,
            "rr": round(rr, 3),
            "confidence_band": confidence.band,
            "confidence_score": confidence.score,
            "note": case.get("note", ""),
        })

    n = len(cases)
    return {
        "total": n,
        "recall@3": round(recall_hits / n, 3),
        "mrr": round(mrr_sum / n, 3),
        "results": results,
    }


def main():
    report = evaluate()
    print("=" * 70)
    print(f"  Alert-Path Evaluation ({report['total']} alert-shaped cases)")
    print("=" * 70)
    print(f"  Recall@3: {report['recall@3']:.1%}")
    print(f"  MRR:      {report['mrr']:.3f}")
    print("=" * 70)
    print("\nPer-case (confidence band is informational, NOT scored into recall/MRR):")
    for r in report["results"]:
        mark = "PASS" if r["recall@3"] else "FAIL"
        score_str = f"{r['confidence_score']:.2f}" if r["confidence_score"] is not None else "None"
        print(f"  [{mark}] rr={r['rr']:.2f} | {r['name']:32s} | family={r['error_family']:26s} "
              f"| band={r['confidence_band']:6s} score={score_str} | top3={r['top3']}")
        print(f"         {r['note']}")


if __name__ == "__main__":
    main()
