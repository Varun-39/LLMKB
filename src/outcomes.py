"""
SQLite outcomes store — one row per incident, sourced from wiki/Incidents/
frontmatter (error_family, resolution_runbook, resolution_outcome).

Derived, not authoritative (R4): wiki/Incidents/ frontmatter is the source of
truth. This table exists because cohort aggregation (how many incidents in
error_family X actually resolved via runbook Y) is a relational query, not a
vector-similarity one — running it against ChromaDB metadata per alert would
mean re-scanning and re-aggregating the whole corpus in Python on every request.
Same idiom as src/manifest.py (SQLite, create-if-missing, per-call connections).

Rebuild after any enrichment change to wiki/Incidents/ frontmatter:
    python -m src.outcomes
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.config import OUTCOMES_DB, WIKI_SOURCE_DIR
from src.loader import parse_frontmatter

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "confidence.yaml"


def load_confidence_config() -> dict:
    """Load cohort/confidence rules from YAML. Shared by P2's past_fix_success
    signal and P3's confidence computation, so a cohort means the same thing
    in both places. Falls back to a minimal built-in set if the file is missing."""
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    # ponytail: minimal fallback if config file is missing
    return {
        "bands": {"high": {"min_score": 0.85}, "medium": {"min_score": 0.60}, "low": {"min_score": 0.35}},
        "min_cohort_size": 3,
        "exclude_outcomes": ["unknown"],
        "count_as_success": ["resolved"],
        "count_as_attempt": ["resolved", "partial", "failed"],
        "require_same_runbook": True,
        "no_match_message": "No strong knowledge match found.",
        "treat_low_as_no_action": False,
    }


CONFIG = load_confidence_config()


def get_connection() -> sqlite3.Connection:
    """Get SQLite connection, creating the DB and table if needed."""
    conn = sqlite3.connect(OUTCOMES_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outcomes (
            incident_id        TEXT PRIMARY KEY,
            error_family       TEXT NOT NULL,
            service            TEXT NOT NULL,
            resolution_runbook TEXT,
            resolution_outcome TEXT NOT NULL,
            date               TEXT,
            rebuilt_at         TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def build_outcomes_db() -> int:
    """
    Rebuild the outcomes table from wiki/Incidents/*.md frontmatter.
    Full rebuild every time (small corpus, correctness over incremental
    complexity) — always reflects the current state of wiki/ exactly.

    Returns the number of incidents loaded.
    """
    incidents_dir = Path(WIKI_SOURCE_DIR) / "Incidents"
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for path in sorted(incidents_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(raw)

        incident_id = meta.get("id")
        error_family = meta.get("error_family")
        resolution_outcome = meta.get("resolution_outcome")
        if not incident_id or not error_family or not resolution_outcome:
            # Incomplete enrichment — skip rather than insert a half-populated
            # row that would silently corrupt cohort counts.
            continue

        rows.append((
            incident_id,
            error_family,
            str(meta.get("service", "general")).lower(),
            meta.get("resolution_runbook"),
            resolution_outcome,
            str(meta.get("date", "")),
            now,
        ))

    conn = get_connection()
    conn.execute("DELETE FROM outcomes")
    conn.executemany(
        """
        INSERT INTO outcomes
            (incident_id, error_family, service, resolution_runbook, resolution_outcome, date, rebuilt_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return len(rows)


def cohort_counts(error_family: str, count_as_success: list[str], count_as_attempt: list[str],
                   resolution_runbook: str | None = None) -> dict:
    """
    Query cohort stats for a given error_family, optionally scoped to a
    specific resolution_runbook (D1's require_same_runbook). When scoped, BOTH
    the numerator and denominator are scoped to that runbook together — this
    answers "does THIS runbook have a good track record", not a mixed-scope
    ratio of "family-wide attempts" over "this runbook's successes" (the two
    don't compose into a meaningful number if attempts and successes are
    counted over different populations).
    """
    conn = get_connection()

    where_scope = "error_family = ?"
    scope_params: list = [error_family]
    if resolution_runbook is not None:
        where_scope += " AND resolution_runbook = ?"
        scope_params.append(resolution_runbook)

    placeholders_attempt = ",".join("?" * len(count_as_attempt))
    total_n = conn.execute(
        f"SELECT COUNT(*) AS n FROM outcomes WHERE {where_scope} AND resolution_outcome IN ({placeholders_attempt})",
        (*scope_params, *count_as_attempt),
    ).fetchone()["n"]

    placeholders_success = ",".join("?" * len(count_as_success))
    success_n = conn.execute(
        f"SELECT COUNT(*) AS n FROM outcomes WHERE {where_scope} AND resolution_outcome IN ({placeholders_success})",
        (*scope_params, *count_as_success),
    ).fetchone()["n"]

    excluded_unknown_n = conn.execute(
        f"SELECT COUNT(*) AS n FROM outcomes WHERE {where_scope} AND resolution_outcome NOT IN ({placeholders_attempt})",
        (*scope_params, *count_as_attempt),
    ).fetchone()["n"]
    conn.close()

    return {
        "prior_success_n": success_n,
        "prior_total_n": total_n,
        "excluded_unknown_n": excluded_unknown_n,
    }


def get_stats() -> dict:
    """Summary stats — count per error_family, count per resolution_outcome."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) AS n FROM outcomes").fetchone()["n"]
    by_family = conn.execute(
        "SELECT error_family, COUNT(*) AS n FROM outcomes GROUP BY error_family ORDER BY n DESC"
    ).fetchall()
    by_outcome = conn.execute(
        "SELECT resolution_outcome, COUNT(*) AS n FROM outcomes GROUP BY resolution_outcome ORDER BY n DESC"
    ).fetchall()
    conn.close()
    return {
        "total": total,
        "by_error_family": {r["error_family"]: r["n"] for r in by_family},
        "by_resolution_outcome": {r["resolution_outcome"]: r["n"] for r in by_outcome},
    }


if __name__ == "__main__":
    n = build_outcomes_db()
    print(f"outcomes.db rebuilt: {n} incidents loaded.")
    stats = get_stats()
    print(f"Total: {stats['total']}")
    print("By error_family:", stats["by_error_family"])
    print("By resolution_outcome:", stats["by_resolution_outcome"])
