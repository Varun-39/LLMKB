"""
Self-check for cohort confidence banding (src/confidence.py), specifically the
low-confidence reconciliation against the pitch deck: deck slide 10 has no
separate 'low' tier ("low = no strong knowledge match found"), so
config/confidence.yaml's treat_low_as_no_action must be true and a
low-scoring cohort must come back as band 'none', not 'low'.

No ChromaDB/Ollama/outcomes.db required — cohort_counts() is monkeypatched
directly so this only exercises the banding logic itself. Run:
    python -m tests.test_confidence
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import confidence


def check_low_band_is_demoted_to_none() -> None:
    assert confidence.TREAT_LOW_AS_NO_ACTION is True, (
        "config/confidence.yaml's treat_low_as_no_action must be true — "
        "the deck's confidence story has no separate 'low' tier"
    )

    # 4 of 10 resolved (ratio 0.4) sits in the 'low' band (0.35 <= score < 0.60)
    # per config/confidence.yaml's bands, and clears min_cohort_size (3).
    with patch.object(
        confidence,
        "cohort_counts",
        return_value={"prior_success_n": 4, "prior_total_n": 10, "excluded_unknown_n": 0},
    ):
        result = confidence.compute_confidence("oom", "RB-001")

    assert result.score == 0.4, f"expected raw score 0.4 (still reported for audit), got {result.score}"
    assert result.band == "none", (
        f"a 'low'-scoring cohort must be demoted to band 'none' (deck reconciliation), got '{result.band}'"
    )
    print(f"OK  low-scoring cohort (score={result.score}) demoted to band='{result.band}'")


def check_medium_band_is_unaffected() -> None:
    # 7 of 10 resolved (ratio 0.7) sits in 'medium' (0.60 <= score < 0.85) —
    # demotion must only touch 'low', nothing else.
    with patch.object(
        confidence,
        "cohort_counts",
        return_value={"prior_success_n": 7, "prior_total_n": 10, "excluded_unknown_n": 0},
    ):
        result = confidence.compute_confidence("oom", "RB-001")

    assert result.band == "medium", f"medium-band cohort must be untouched by the low->none demotion, got '{result.band}'"
    print(f"OK  medium-scoring cohort (score={result.score}) stays band='{result.band}'")


def main():
    check_low_band_is_demoted_to_none()
    check_medium_band_is_unaffected()
    print("\nconfidence banding checks passed")


if __name__ == "__main__":
    main()
