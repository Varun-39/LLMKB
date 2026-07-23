"""
Self-check for src/card.py's RecommendationCard — recommended_runbook field
and the R2 grounding invariants. No ChromaDB/Ollama required.
Run:
    python -m tests.test_card
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from src.card import Confidence, DetectedIssue, Evidence, RecommendationCard, Risk

DETECTED = DetectedIssue(error="oom", component="svc", host="h1", environment="prod", raw_message="msg")
EVIDENCE = [Evidence(doc_id="RB-001", doc_type="runbook", section="mitigation", snippet="s", why_matched="w", signal_scores={})]


def main():
    card = RecommendationCard(
        correlation_id="c1", signature_id="s1", detected_issue=DETECTED,
        recommended_action="do the thing", recommended_runbook="RB-001",
        evidence=EVIDENCE, confidence=Confidence(band="high", prior_success_n=1, prior_total_n=1, cohort_size=1, excluded_unknown_n=0),
        risk=Risk(level="low"),
    )
    assert card.recommended_runbook == "RB-001"
    print("OK  recommended_runbook is settable and readable")

    round_tripped = RecommendationCard.model_validate_json(card.model_dump_json())
    assert round_tripped.recommended_runbook == "RB-001", "recommended_runbook must survive the cache's JSON round-trip"
    print("OK  recommended_runbook survives model_dump_json -> model_validate_json (recommendation_cache's round-trip)")

    none_conf = Confidence(band="none", prior_success_n=0, prior_total_n=0, cohort_size=0, excluded_unknown_n=0)
    no_match = RecommendationCard(
        correlation_id="c2", signature_id="s2", detected_issue=DETECTED,
        recommended_action=None, recommended_runbook="RB-002",  # a near-miss runbook may still be recorded
        evidence=[], confidence=none_conf, risk=Risk(level="unknown"),
    )
    assert no_match.recommended_runbook == "RB-002"
    print("OK  recommended_runbook may be set even when band='none' and recommended_action=None")

    try:
        RecommendationCard(
            correlation_id="c3", signature_id="s3", detected_issue=DETECTED,
            recommended_action="do the thing", evidence=[],
            confidence=Confidence(band="high", prior_success_n=1, prior_total_n=1, cohort_size=1, excluded_unknown_n=0),
            risk=Risk(level="low"),
        )
        raise AssertionError("expected R2 violation: action with empty evidence")
    except ValidationError:
        print("OK  R2 invariant still enforced: action + empty evidence raises")

    try:
        RecommendationCard(
            correlation_id="c4", signature_id="s4", detected_issue=DETECTED,
            recommended_action="do the thing", evidence=EVIDENCE, confidence=none_conf,
            risk=Risk(level="low"),
        )
        raise AssertionError("expected R2 violation: band=none with non-null action")
    except ValidationError:
        print("OK  R2 invariant still enforced: band='none' + non-null action raises")

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
