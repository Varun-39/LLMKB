"""
SQLite Manifest — tracks indexed documents for delta re-indexing.

Records:
- object_key: MinIO path
- content_hash: SHA-256 of file content
- chunk_count: number of chunks generated
- last_indexed: timestamp of last successful indexing

Allows the pipeline to skip unchanged documents and only re-embed deltas.
"""

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.config import MANIFEST_DB


def get_connection() -> sqlite3.Connection:
    """Get SQLite connection, creating the DB and table if needed."""
    conn = sqlite3.connect(MANIFEST_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            object_key TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            doc_type TEXT DEFAULT '',
            last_indexed TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def compute_hash(content: str) -> str:
    """Compute SHA-256 hash of content string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_changed(object_key: str, content: str) -> bool:
    """
    Check if a document has changed since last indexing.
    
    Returns True if:
    - Document is not in manifest (new file)
    - Document hash differs from stored hash (content changed)
    """
    current_hash = compute_hash(content)

    conn = get_connection()
    row = conn.execute(
        "SELECT content_hash FROM documents WHERE object_key = ?",
        (object_key,),
    ).fetchone()
    conn.close()

    if row is None:
        return True  # New file
    return row["content_hash"] != current_hash


def record_indexed(object_key: str, content: str, chunk_count: int, doc_type: str = "") -> None:
    """Record that a document was successfully indexed."""
    content_hash = compute_hash(content)
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO documents (object_key, content_hash, chunk_count, doc_type, last_indexed)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(object_key) DO UPDATE SET
            content_hash = excluded.content_hash,
            chunk_count = excluded.chunk_count,
            doc_type = excluded.doc_type,
            last_indexed = excluded.last_indexed
        """,
        (object_key, content_hash, chunk_count, doc_type, now),
    )
    conn.commit()
    conn.close()


def remove_from_manifest(object_key: str) -> None:
    """Remove a document from the manifest (when it's deleted from source)."""
    conn = get_connection()
    conn.execute("DELETE FROM documents WHERE object_key = ?", (object_key,))
    conn.commit()
    conn.close()


def get_all_indexed_keys() -> set[str]:
    """Get all object keys currently in the manifest."""
    conn = get_connection()
    rows = conn.execute("SELECT object_key FROM documents").fetchall()
    conn.close()
    return {row["object_key"] for row in rows}


def get_manifest_stats() -> dict:
    """Get summary stats from the manifest."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()["cnt"]
    by_type = conn.execute(
        "SELECT doc_type, COUNT(*) as cnt FROM documents GROUP BY doc_type"
    ).fetchall()
    conn.close()

    return {
        "total_documents": total,
        "by_type": {row["doc_type"]: row["cnt"] for row in by_type},
    }


def reset_manifest() -> None:
    """Clear the manifest completely (forces full re-index on next run)."""
    conn = get_connection()
    conn.execute("DELETE FROM documents")
    conn.commit()
    conn.close()
    print("  Manifest cleared — next ingest will be a full re-index.")
