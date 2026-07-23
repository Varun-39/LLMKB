"""
SQLite recommendation cache — keyed by alert fingerprint signature_id.

An identical recurring incident (same error_family + service + stack anchor)
shouldn't re-pay full retrieval + scoring + LLM phrasing every time. On a
signature match, /alert returns the last card instantly instead of re-running
the pipeline; hit_count also gives the "N of M prior incidents resolved this
way" stat visibility, alongside confidence's own cohort counts.

Stores the full RecommendationCard as JSON (card is the complete answer —
action, evidence, confidence, risk — there's no narrower "answer" string
separate from it anymore).

Same pattern as src/manifest.py (SQLite, create-if-missing, per-call connections).
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.config import RECOMMENDATION_CACHE_DB


def get_connection() -> sqlite3.Connection:
    """Get SQLite connection, creating the DB and table if needed."""
    conn = sqlite3.connect(RECOMMENDATION_CACHE_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            signature_id TEXT PRIMARY KEY,
            error_family TEXT NOT NULL,
            service TEXT NOT NULL,
            card_json TEXT NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


@dataclass
class CachedRecommendation:
    signature_id: str
    error_family: str
    service: str
    card_json: str
    hit_count: int


def get_cached(signature_id: str) -> Optional[CachedRecommendation]:
    """Look up a cached recommendation and bump its hit count. None on miss."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM recommendations WHERE signature_id = ?", (signature_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return None

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE recommendations SET hit_count = hit_count + 1, last_used_at = ? WHERE signature_id = ?",
        (now, signature_id),
    )
    conn.commit()
    conn.close()

    return CachedRecommendation(
        signature_id=row["signature_id"],
        error_family=row["error_family"],
        service=row["service"],
        card_json=row["card_json"],
        hit_count=row["hit_count"] + 1,
    )


def store(signature_id: str, error_family: str, service: str, card_json: str) -> None:
    """Cache a freshly assembled card under its fingerprint signature."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO recommendations
            (signature_id, error_family, service, card_json, hit_count, created_at, last_used_at)
        VALUES (?, ?, ?, ?, 0, ?, ?)
        ON CONFLICT(signature_id) DO UPDATE SET
            card_json = excluded.card_json,
            last_used_at = excluded.last_used_at
        """,
        (signature_id, error_family, service, card_json, now, now),
    )
    conn.commit()
    conn.close()


def reset_cache() -> None:
    """Clear the recommendation cache (e.g. after a KB re-index changes what's grounded)."""
    conn = get_connection()
    conn.execute("DELETE FROM recommendations")
    conn.commit()
    conn.close()
