"""
Self-check for src/recommendation_cache.py — SQLite cache keyed by
fingerprint signature_id, no ChromaDB/Ollama required.

Runs against a throwaway DB file (never the real recommendations.db) so it's
safe to run repeatedly. Run:
    python -m tests.test_recommendation_cache
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db = Path(tempfile.gettempdir()) / "llmkb_test_recommendation_cache.db"
if _tmp_db.exists():
    _tmp_db.unlink()

from src import recommendation_cache as cache
cache.RECOMMENDATION_CACHE_DB = str(_tmp_db)  # redirect get_connection() at the module-global it reads


def main():
    sig = "abc123def456"

    assert cache.get_cached(sig) is None, "expected a miss on an empty cache"
    print("OK  miss on empty cache")

    citations = [{"doc_id": "INC-009", "doc_type": "incident", "section": "resolution",
                  "service": "reporting-service", "score": 0.95, "score_explain": None}]
    cache.store(
        signature_id=sig, error_family="connection-pool-exhausted", service="reporting-service",
        query="ReportingService is reporting a pool timeout", answer="Terminate idle connections.",
        citations=citations,
    )
    print("OK  store()")

    hit = cache.get_cached(sig)
    assert hit is not None, "expected a hit after store()"
    assert hit.hit_count == 1, f"expected hit_count=1, got {hit.hit_count}"
    assert hit.answer == "Terminate idle connections."
    assert hit.citations == citations
    print(f"OK  hit #1: {hit.answer!r}")

    hit2 = cache.get_cached(sig)
    assert hit2.hit_count == 2, f"expected hit_count=2, got {hit2.hit_count}"
    print(f"OK  hit #2: hit_count now {hit2.hit_count}")

    # Re-storing under the same signature updates the answer without resetting hit_count.
    cache.store(
        signature_id=sig, error_family="connection-pool-exhausted", service="reporting-service",
        query="ReportingService is reporting a pool timeout", answer="Updated guidance.",
        citations=citations,
    )
    hit3 = cache.get_cached(sig)
    assert hit3.answer == "Updated guidance.", "expected re-store to overwrite the answer"
    assert hit3.hit_count == 3, f"expected hit_count=3 (not reset by re-store), got {hit3.hit_count}"
    print(f"OK  re-store overwrites answer, preserves hit_count ({hit3.hit_count})")

    cache.reset_cache()
    assert cache.get_cached(sig) is None, "expected a miss after reset_cache()"
    print("OK  reset_cache() clears the table")

    _tmp_db.unlink(missing_ok=True)
    print("\nAll recommendation_cache checks passed")


if __name__ == "__main__":
    main()
