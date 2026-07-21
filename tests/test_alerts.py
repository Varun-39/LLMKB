"""
Self-check for synthetic alert intake (src/alerts.py + data/sample_alerts/*.json).

Verifies each sample fixture parses as a SplunkAlert, builds a sane query,
and fingerprints to a KNOWN error family (not "unknown") — i.e. the demo
alerts actually exercise src/fingerprint.py's classification rules instead
of silently falling through.

No ChromaDB/Ollama required — this only covers the parts of the /alert
endpoint that don't need the running index. Run:
    python -m tests.test_alerts
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.alerts import SplunkAlert, alert_to_query
from src.fingerprint import compute_fingerprint

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_alerts"


def check_fixture(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    alert = SplunkAlert.model_validate(raw)

    query = alert_to_query(alert)
    assert alert.result.component in query, f"{path.name}: component missing from query"
    assert alert.result.message in query, f"{path.name}: message missing from query"

    fp = compute_fingerprint(
        raw_text=alert.result.message,
        service=alert.result.service,
        environment=alert.result.environment,
        stack_trace=alert.result.stack_trace,
    )
    assert fp.error_family != "unknown", f"{path.name}: fingerprint matched no error family"
    assert fp.signature_id, f"{path.name}: missing signature_id"

    # Fingerprint-enriched query must carry the error_family and, when a stack
    # trace produced a root_frame, the exact frame text — this is what lets
    # BM25 key off the application class/method instead of just the paraphrase.
    enriched = alert_to_query(alert, fingerprint=fp)
    assert fp.error_family.replace("-", " ") in enriched, f"{path.name}: error_family missing from enriched query"
    if fp.root_frame:
        assert fp.root_frame in enriched, f"{path.name}: root_frame missing from enriched query"

    print(f"OK  {path.name:40s} family={fp.error_family:28s} sig={fp.signature_id}  root_frame={'yes' if fp.root_frame else 'no'}")


def main():
    fixtures = sorted(FIXTURES_DIR.glob("*.json"))
    assert fixtures, f"no sample alerts found in {FIXTURES_DIR}"
    for path in fixtures:
        check_fixture(path)
    print(f"\n{len(fixtures)} sample alert(s) OK")


if __name__ == "__main__":
    main()
