"""
J1 — replay accuracy harness. Validates recommendation correctness and
confidence calibration at 100-incident scale, instead of the 7 hand-picked
cases tests/evaluate_alert_path.py covers.

For each incident with a known (non-"unknown") error_family, builds a
synthetic alert from that incident's OWN Summary+Symptoms text ONLY
(excluding Diagnosis/Resolution/Post-Incident-Review, so the alert doesn't
trivially contain its own answer), runs it through the real alert pipeline
(fingerprint -> AlertContext -> retrieve_only, generation OFF, mirroring
tests/evaluate_alert_path.py's pattern), and checks whether the implied
recommended runbook matches the incident's own resolution_runbook.

47 of 100 incidents have error_family: unknown in frontmatter — a real,
expected ground-truth value (not missing data), but one that can't be
meaningfully fingerprint-matched against a taxonomy that doesn't cover it.
These are excluded from the scored set; the exclusion count is reported
separately, never silently dropped.

The remaining 53 scoreable incidents are split 80/20 (deterministic seed) —
splitting happens AFTER filtering out "unknown" incidents, giving a stable
~42/11 split every run, rather than a variable (and possibly much smaller)
holdout that splitting-then-filtering would produce.

This harness does not tune any config/scoring value against its own results.

Run:
    python -m tests.evaluate_replay
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import init_llama_index_settings
from src.loader import parse_frontmatter
from src.chunker import split_by_sections, normalize_section_name
from src.alerts import SplunkAlert, SplunkResult, alert_to_query, build_alert_context
from src.fingerprint import compute_fingerprint
from src.query import retrieve_only, FINAL_TOP_K_DEFAULT
from src.confidence import compute_confidence
from src.recommendation import _find_recommended_runbook

INCIDENTS_DIR = Path(__file__).resolve().parent.parent / "wiki" / "Incidents"
SUMMARY_SYMPTOM_SECTIONS = {"summary", "symptoms"}


def extract_summary_symptoms(body: str) -> str:
    """Summary+Symptoms only — excludes Diagnosis/Resolution/Post-Incident-Review
    so the synthetic alert doesn't trivially contain its own answer."""
    parts = [
        section_body for header, section_body in split_by_sections(body)
        if normalize_section_name(header) in SUMMARY_SYMPTOM_SECTIONS
    ]
    return "\n\n".join(parts).strip()


def synthetic_alert_for_incident(path: Path) -> tuple[SplunkAlert, dict]:
    """Build a SplunkAlert from an incident's own Summary+Symptoms text.
    Only service/environment/message are scored inputs — sid/search_name/
    host/component/source/_time are inert placeholders nothing downstream
    compares against ground truth."""
    content = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)
    message = extract_summary_symptoms(body)

    alert = SplunkAlert(
        sid=f"replay-{meta['id']}",
        search_name=f"J1-Replay-{meta['id']}",
        result=SplunkResult(
            _time="2026-01-01T00:00:00Z",
            host="replay-host-01",
            source="replay",
            component=meta.get("service", "unknown"),
            service=meta["service"],
            environment=meta.get("environment", "prod"),
            message=message,
        ),
    )
    return alert, meta


def load_split(seed: int = 42) -> tuple[list[Path], list[Path], list[Path]]:
    """Filter to scoreable (non-'unknown' error_family) incidents FIRST, then
    split 80/20 — a deterministic ~42/11 split, not a variable one."""
    all_paths = sorted(INCIDENTS_DIR.glob("*.md"))
    assert len(all_paths) == 100, f"expected 100 incidents, found {len(all_paths)}"

    scoreable, excluded_unknown = [], []
    for p in all_paths:
        meta, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
        (excluded_unknown if meta.get("error_family") == "unknown" else scoreable).append(p)

    rng = random.Random(seed)
    shuffled = scoreable[:]
    rng.shuffle(shuffled)
    split_idx = round(len(shuffled) * 0.8)
    training, holdout = shuffled[:split_idx], shuffled[split_idx:]

    assert len(training) + len(holdout) + len(excluded_unknown) == 100
    assert not (set(training) & set(holdout))
    return training, holdout, excluded_unknown


def replay_one(path: Path, top_k: int = FINAL_TOP_K_DEFAULT) -> dict:
    alert, meta = synthetic_alert_for_incident(path)
    fp = compute_fingerprint(
        raw_text=alert.result.message, service=alert.result.service,
        environment=alert.result.environment, stack_trace=None,
    )
    ctx = build_alert_context(alert, fp)
    query_text = alert_to_query(alert, fingerprint=fp)
    nodes = retrieve_only(query_text, top_k=top_k, service=alert.result.service, alert_context=ctx)

    implied_runbook = _find_recommended_runbook(nodes)
    confidence = compute_confidence(ctx.error_family, implied_runbook)

    return {
        "incident_id": meta["id"],
        "ground_truth_error_family": meta.get("error_family"),
        "ground_truth_runbook": meta.get("resolution_runbook"),
        "fingerprint_error_family": fp.error_family,
        "implied_runbook": implied_runbook,
        "band": confidence.band,
    }


def compute_metrics(results: list[dict]) -> dict:
    """correct / no_match / false_match partition the result set exactly
    (every result falls into exactly one bucket)."""
    n = len(results)
    correct = [r for r in results if r["band"] != "none" and r["implied_runbook"] == r["ground_truth_runbook"]]
    no_match = [r for r in results if r["band"] == "none"]
    false_match = [r for r in results if r["band"] != "none" and r["implied_runbook"] != r["ground_truth_runbook"]]
    assert len(correct) + len(no_match) + len(false_match) == n

    by_band = {}
    for band in ("high", "medium", "low"):
        band_results = [r for r in results if r["band"] == band]
        band_correct = [r for r in band_results if r["implied_runbook"] == r["ground_truth_runbook"]]
        by_band[band] = {
            "n": len(band_results),
            "correct_rate": (len(band_correct) / len(band_results)) if band_results else None,
        }

    return {
        "n": n,
        "action_correctness@1": round(len(correct) / n, 3) if n else None,
        "no_match_rate": round(len(no_match) / n, 3) if n else None,
        "false_match_rate": round(len(false_match) / n, 3) if n else None,
        "by_band": by_band,
    }


def print_report(label: str, results: list[dict]) -> None:
    metrics = compute_metrics(results)
    print(f"\n--- {label} (N={metrics['n']}) ---")
    print(f"  action_correctness@1: {metrics['action_correctness@1']:.1%}")
    print(f"  no_match_rate:        {metrics['no_match_rate']:.1%}")
    print(f"  false_match_rate:     {metrics['false_match_rate']:.1%}")
    print("  confidence calibration (informational — correctness rate by band):")
    for band, stats in metrics["by_band"].items():
        rate_str = f"{stats['correct_rate']:.1%}" if stats["correct_rate"] is not None else "n/a (0 cases)"
        print(f"    {band:8s} n={stats['n']:3d}  correct_rate={rate_str}")


def main():
    init_llama_index_settings()

    training, holdout, excluded = load_split()
    print(f"Split: {len(training)} training, {len(holdout)} holdout, {len(excluded)} excluded (error_family=unknown)")

    print("\nReplaying holdout set...")
    holdout_results = [replay_one(p) for p in holdout]

    print("Replaying training set...")
    training_results = [replay_one(p) for p in training]

    all_scoreable_results = holdout_results + training_results

    print("=" * 70)
    print("  J1 Replay Accuracy — HEADLINE (held-out set, never used for debugging)")
    print("=" * 70)
    print_report("Holdout", holdout_results)

    print("\n" + "=" * 70)
    print("  J1 Replay Accuracy — INFORMATIONAL (full scoreable set, 80+20)")
    print("=" * 70)
    print_report("Full scoreable set", all_scoreable_results)

    print(f"\n{len(excluded)} incidents excluded (error_family=unknown at ground truth) — not scored, listed below:")
    for p in excluded:
        meta, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
        print(f"  {meta['id']}")


if __name__ == "__main__":
    main()
