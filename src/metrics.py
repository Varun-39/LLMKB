"""
Feedback rollup metrics — the pitch deck's "Observability" guardrail (slide
10) names precision, acceptance rate, false matches, KB gaps and time saved
as what Phase 1 should track. Nothing previously aggregated feedback.db into
any of these; this module does, from what's actually stored there.

time_saved is deliberately NOT computed as a number — feedback.db records
decided_at but never the alert's original intake time, so "time to decision"
(and therefore time saved against the deck's own 10-15 min manual baseline)
isn't derivable from current data. TIME_SAVED_NOTE says so explicitly rather
than reporting a made-up figure; computing it for real needs the alert
receipt time persisted somewhere (e.g. on the RecommendationCard or in
recommendation_cache.db), which is future instrumentation, not a rollup.

"Precision" from the same slide isn't computed either, for the same reason:
it needs an independent correctness label per recommendation (was the action
actually right), which nothing in this repo currently captures — accept/edit
vs. reject is an ops *preference* signal, not a verified-correct label.

Usage:
    python -m src.metrics
"""

from dataclasses import dataclass, field
from typing import Optional

from src.feedback import get_connection

TIME_SAVED_NOTE = (
    "not measured: feedback.db has decided_at but not the alert's original intake "
    "time, so time-to-decision (and time saved vs. the deck's 10-15 min manual "
    "baseline) can't be computed from current data without persisting alert "
    "receipt time — flagged as unmeasured rather than estimated"
)

PRECISION_NOTE = (
    "not measured: precision needs an independent correctness label per "
    "recommendation; accept/edit vs. reject is an ops preference signal, not a "
    "verified-correct one"
)


@dataclass
class MetricsRollup:
    total_decisions: int
    by_decision: dict = field(default_factory=dict)
    by_error_family: dict = field(default_factory=dict)
    acceptance_rate: Optional[float] = None    # (accept + edit) / total — recommendation was used, as-is or amended
    false_match_rate: Optional[float] = None   # reject / total — proxy for "recommendation was wrong"
    escalate_rate: Optional[float] = None
    kb_gap_count: int = 0
    time_saved: str = TIME_SAVED_NOTE
    precision: str = PRECISION_NOTE


def compute_rollup() -> MetricsRollup:
    conn = get_connection()
    rows = conn.execute("SELECT decision, error_family FROM feedback").fetchall()
    conn.close()

    total = len(rows)
    by_decision: dict = {}
    by_error_family: dict = {}
    for r in rows:
        by_decision[r["decision"]] = by_decision.get(r["decision"], 0) + 1
        fam = r["error_family"] or "unknown"
        by_error_family[fam] = by_error_family.get(fam, 0) + 1

    def rate(n: int) -> Optional[float]:
        return round(n / total, 4) if total else None

    accepted = by_decision.get("accept", 0) + by_decision.get("edit", 0)
    rejected = by_decision.get("reject", 0)
    escalated = by_decision.get("escalate", 0)

    return MetricsRollup(
        total_decisions=total,
        by_decision=by_decision,
        by_error_family=by_error_family,
        acceptance_rate=rate(accepted),
        false_match_rate=rate(rejected),
        escalate_rate=rate(escalated),
        kb_gap_count=by_decision.get("kb_gap", 0),
    )


def main():
    r = compute_rollup()
    print(f"Total decisions:   {r.total_decisions}")
    print(f"By decision:       {r.by_decision}")
    print(f"By error_family:   {r.by_error_family}")
    print(f"Acceptance rate:   {r.acceptance_rate}")
    print(f"False match rate:  {r.false_match_rate}")
    print(f"Escalate rate:     {r.escalate_rate}")
    print(f"KB gap count:      {r.kb_gap_count}")
    print(f"Time saved:        {r.time_saved}")
    print(f"Precision:         {r.precision}")


if __name__ == "__main__":
    main()
