"""
Self-check for src/metrics.py — feedback.db rollup, no ChromaDB/Ollama
required.

Runs against a throwaway DB file (never the real feedback.db) so it's safe
to run repeatedly. Run:
    python -m tests.test_metrics
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db = Path(tempfile.gettempdir()) / "llmkb_test_feedback.db"
if _tmp_db.exists():
    _tmp_db.unlink()

from src import feedback
feedback.FEEDBACK_DB = str(_tmp_db)  # redirect get_connection() at the module-global it reads

from src import metrics


def main():
    empty = metrics.compute_rollup()
    assert empty.total_decisions == 0
    assert empty.acceptance_rate is None, "rate must be None (not 0/0) with no decisions yet"
    print("OK  empty feedback.db -> zero decisions, rates=None")

    decisions = [
        ("accept", "oom"),
        ("accept", "oom"),
        ("edit", "connection-pool-exhausted"),
        ("reject", "oom"),
        ("escalate", "disk-full"),
        ("kb_gap", "unknown"),
        ("kb_gap", None),
    ]
    for i, (decision, family) in enumerate(decisions):
        feedback.record_feedback(
            correlation_id=f"corr-{i}",
            signature_id=f"sig-{i}",
            error_family=family,
            recommended_runbook="RB-001",
            decision=decision,
            actor="jane.ops",
            comment="test" if decision in ("reject", "escalate", "kb_gap") else None,
            edited_action="do the thing differently" if decision == "edit" else None,
        )

    r = metrics.compute_rollup()
    assert r.total_decisions == 7, f"expected 7, got {r.total_decisions}"
    assert r.by_decision == {"accept": 2, "edit": 1, "reject": 1, "escalate": 1, "kb_gap": 2}, r.by_decision
    # acceptance = (accept 2 + edit 1) / 7
    assert r.acceptance_rate == round(3 / 7, 4), r.acceptance_rate
    # false_match = reject 1 / 7
    assert r.false_match_rate == round(1 / 7, 4), r.false_match_rate
    assert r.escalate_rate == round(1 / 7, 4), r.escalate_rate
    assert r.kb_gap_count == 2, r.kb_gap_count
    assert r.by_error_family.get("unknown") == 2, "None and 'unknown' error_family both bucket under 'unknown'"
    print(f"OK  7 decisions -> acceptance_rate={r.acceptance_rate} false_match_rate={r.false_match_rate} kb_gap_count={r.kb_gap_count}")

    # Never fabricate time_saved/precision numbers — must stay explicit notes.
    assert "not measured" in r.time_saved
    assert "not measured" in r.precision
    print("OK  time_saved/precision remain explicit 'not measured' notes, not fabricated numbers")

    _tmp_db.unlink(missing_ok=True)
    print("\nAll metrics rollup checks passed")


if __name__ == "__main__":
    main()
