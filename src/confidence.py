"""
Cohort-based confidence computation (P3).

Reads ONLY src.outcomes.cohort_counts() — outcomes.db, derived from
wiki/Incidents/ frontmatter. There is NO code path here that reads embedding
similarity, retrieval score, RRF, or reranker output; the only inputs are
error_family and resolution_runbook (both structured facts, not scores).

D4's structural guarantee (impossible to construct a card with band='none'
and a non-null action, or a non-null action with empty evidence) is enforced
by src.card.RecommendationCard's validators, not here — that check needs the
whole card shape (action + evidence + confidence together), which is P4's
concern. This module only produces the Confidence value itself.
"""

from dataclasses import dataclass
from typing import Optional

from src.outcomes import CONFIG, cohort_counts

BANDS = CONFIG["bands"]  # {high: {min_score}, medium: {...}, low: {...}} - config/confidence.yaml
MIN_COHORT_SIZE = CONFIG["min_cohort_size"]
COUNT_AS_SUCCESS = CONFIG["count_as_success"]
COUNT_AS_ATTEMPT = CONFIG["count_as_attempt"]
REQUIRE_SAME_RUNBOOK = CONFIG.get("require_same_runbook", True)
TREAT_LOW_AS_NO_ACTION = CONFIG.get("treat_low_as_no_action", False)
NO_MATCH_MESSAGE = CONFIG.get("no_match_message", "No strong knowledge match found.")

# Bands checked in this fixed descending order — a score must clear the
# highest band's min_score to earn it. Order come from BANDS dict itself
# (config/confidence.yaml), not hardcoded band names beyond this ordering.
_BAND_ORDER = ("high", "medium", "low")


@dataclass
class Confidence:
    band: str                      # 'high' | 'medium' | 'low' | 'none'
    score: Optional[float]         # prior_success_n / prior_total_n; None only if prior_total_n == 0
    prior_success_n: int
    prior_total_n: int
    cohort_size: int                # == prior_total_n, exposed under the deck's own field name
    excluded_unknown_n: int          # D2: 'unknown'-outcome incidents in this same scope, visible on the card


def _band_for_score(score: float) -> str:
    for name in _BAND_ORDER:
        if name in BANDS and score >= BANDS[name]["min_score"]:
            return name
    return "none"


def compute_confidence(error_family: Optional[str], resolution_runbook: Optional[str]) -> Confidence:
    """
    D1: score = prior_success_n / prior_total_n, sourced entirely from
        outcomes.db via cohort_counts() (never embedding/retrieval/RRF/reranker).
    D2: 'unknown'-outcome incidents are excluded from prior_total_n entirely —
        not counted as failures, not silently as successes — and surfaced via
        excluded_unknown_n rather than hidden.
    D3: cohort_size < min_cohort_size => band 'none', regardless of ratio (the
        ratio itself is still reported — for transparency, e.g. "1 of 1, but
        too few to judge" is more honest than hiding the number outright — it
        is the BAND, not the score, that gates whether the card acts on it).
    """
    if not error_family or error_family == "unknown" or not resolution_runbook:
        return Confidence(band="none", score=None, prior_success_n=0, prior_total_n=0,
                           cohort_size=0, excluded_unknown_n=0)

    counts = cohort_counts(
        error_family,
        count_as_success=COUNT_AS_SUCCESS,
        count_as_attempt=COUNT_AS_ATTEMPT,
        resolution_runbook=resolution_runbook if REQUIRE_SAME_RUNBOOK else None,
    )
    prior_success_n = counts["prior_success_n"]
    prior_total_n = counts["prior_total_n"]
    excluded_unknown_n = counts["excluded_unknown_n"]

    score = (prior_success_n / prior_total_n) if prior_total_n > 0 else None

    if prior_total_n < MIN_COHORT_SIZE:
        band = "none"
    elif score is not None:
        band = _band_for_score(score)
        if band == "low" and TREAT_LOW_AS_NO_ACTION:
            band = "none"
    else:
        band = "none"

    return Confidence(
        band=band,
        score=score,
        prior_success_n=prior_success_n,
        prior_total_n=prior_total_n,
        cohort_size=prior_total_n,
        excluded_unknown_n=excluded_unknown_n,
    )
