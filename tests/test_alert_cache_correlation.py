"""
Self-check: a cache-hit /alert response must carry a FRESH correlation_id
(different from the cache-miss response that first populated the cache),
while the grounded content (recommended_action, evidence, confidence) stays
identical. Requires ChromaDB + Ollama running (same requirement as
tests/evaluate_alert_path.py).

Run:
    python -m tests.test_alert_cache_correlation
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import init_llama_index_settings
from src.alerts import SplunkAlert
from src.server import alert_endpoint
from src import recommendation_cache

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "sample_alerts" / "alert-connection-pool-exhausted.json"


def main():
    init_llama_index_settings()
    recommendation_cache.reset_cache()  # clean slate — don't inherit a hit from a prior run

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    alert = SplunkAlert.model_validate(raw)

    card1 = asyncio.run(alert_endpoint(alert, generation=False))
    card2 = asyncio.run(alert_endpoint(alert, generation=False))

    assert card1.correlation_id != card2.correlation_id, (
        f"correlation_id must differ per request even on a cache hit, got {card1.correlation_id!r} twice"
    )
    assert card1.recommended_action == card2.recommended_action, "cached recommended_action must be reused, not regenerated"
    assert card1.evidence == card2.evidence, "cached evidence must be reused"
    assert card1.confidence == card2.confidence, "cached confidence must be reused"

    print(f"OK  cache MISS correlation_id: {card1.correlation_id}")
    print(f"OK  cache HIT  correlation_id: {card2.correlation_id} (fresh, as expected)")
    print("OK  recommended_action, evidence, confidence unchanged across the cache hit")
    print("\nAll correlation_id/cache-hit checks passed")


if __name__ == "__main__":
    main()
