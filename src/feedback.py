"""
SQLite feedback store — one row per ops decision on a recommendation card
(G1-G4).

Append-only: a card that gets re-decided later (e.g. corrected) gets a NEW
row, never an overwrite — history matters for audit (R8). actor + decided_at
are mandatory; a submission missing either is rejected before it reaches this
store (validate_feedback() runs first, always).

This is the decision plane (R6) — distinct from outcomes.db (knowledge plane,
derived from wiki/) and recommendation_cache.db (a pure cache). Unlike those
two, feedback.db is NOT derived and NOT rebuildable from anything else — it is
itself a system of record and must never be wiped as part of a KB refresh.

Same idiom as src/manifest.py / src/recommendation_cache.py / src/outcomes.py
(SQLite, create-if-missing, per-call connections).
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from src.config import FEEDBACK_DB

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "feedback.yaml"


def load_feedback_config() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    # ponytail: minimal fallback if config file is missing
    return {
        "valid_decisions": ["accept", "edit", "reject", "escalate", "kb_gap"],
        "require_comment_for": ["reject", "escalate", "kb_gap"],
        "edited_action_required_for": ["edit"],
    }


CONFIG = load_feedback_config()
VALID_DECISIONS = CONFIG["valid_decisions"]
REQUIRE_COMMENT_FOR = set(CONFIG["require_comment_for"])
EDITED_ACTION_REQUIRED_FOR = set(CONFIG["edited_action_required_for"])


class FeedbackValidationError(ValueError):
    pass


def get_connection() -> sqlite3.Connection:
    """Get SQLite connection, creating the DB and table if needed."""
    conn = sqlite3.connect(FEEDBACK_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            correlation_id TEXT NOT NULL,
            signature_id TEXT NOT NULL,
            error_family TEXT,
            recommended_runbook TEXT,
            decision TEXT NOT NULL,
            actor TEXT NOT NULL,
            comment TEXT,
            edited_action TEXT,
            decided_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


@dataclass
class FeedbackRecord:
    id: int
    correlation_id: str
    signature_id: str
    error_family: Optional[str]
    recommended_runbook: Optional[str]
    decision: str
    actor: str
    comment: Optional[str]
    edited_action: Optional[str]
    decided_at: str


def validate_feedback(decision: str, actor: Optional[str], comment: Optional[str],
                       edited_action: Optional[str]) -> None:
    """G3/G4: raises FeedbackValidationError on any invalid submission — called
    before persistence, so an invalid decision never reaches feedback.db."""
    if decision not in VALID_DECISIONS:
        raise FeedbackValidationError(f"'{decision}' is not a valid decision — must be one of {VALID_DECISIONS}")
    if not actor or not actor.strip():
        raise FeedbackValidationError("actor is required (R8: every decision must be attributable)")
    if decision in REQUIRE_COMMENT_FOR and not (comment and comment.strip()):
        raise FeedbackValidationError(f"comment is required for decision='{decision}'")
    if decision in EDITED_ACTION_REQUIRED_FOR and not (edited_action and edited_action.strip()):
        raise FeedbackValidationError(f"edited_action is required for decision='{decision}'")


def record_feedback(
    correlation_id: str,
    signature_id: str,
    error_family: Optional[str],
    recommended_runbook: Optional[str],
    decision: str,
    actor: str,
    comment: Optional[str] = None,
    edited_action: Optional[str] = None,
) -> FeedbackRecord:
    """Persist one decision. Always INSERTs a new row (append-only, G2) — never
    UPDATEs a prior decision on the same card, even if correlation_id repeats."""
    validate_feedback(decision, actor, comment, edited_action)

    decided_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO feedback
            (correlation_id, signature_id, error_family, recommended_runbook,
             decision, actor, comment, edited_action, decided_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (correlation_id, signature_id, error_family, recommended_runbook,
         decision, actor, comment, edited_action, decided_at),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()

    return FeedbackRecord(
        id=row_id, correlation_id=correlation_id, signature_id=signature_id,
        error_family=error_family, recommended_runbook=recommended_runbook,
        decision=decision, actor=actor, comment=comment,
        edited_action=edited_action, decided_at=decided_at,
    )


def get_feedback_history(correlation_id: str) -> list[FeedbackRecord]:
    """All decisions ever recorded for a card, oldest first — the audit trail."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM feedback WHERE correlation_id = ? ORDER BY decided_at ASC",
        (correlation_id,),
    ).fetchall()
    conn.close()
    return [FeedbackRecord(**dict(r)) for r in rows]
