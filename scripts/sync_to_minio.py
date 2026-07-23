"""
Sync wiki/ directory to MinIO bucket.

One-way sync: wiki/ (local editing surface) → MinIO (document source of truth for RAG).
Preserves folder structure as object key prefixes.

Usage:
    python scripts/sync_to_minio.py
    python scripts/sync_to_minio.py --dry-run
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
from minio import Minio
from minio.error import S3Error
from src.config import (
    MINIO_ENDPOINT,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    MINIO_BUCKET,
    MINIO_SECURE,
    WIKI_SOURCE_DIR,
)


def get_minio_client() -> Minio:
    """Create and return a MinIO client."""
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def ensure_bucket(client: Minio, bucket: str) -> None:
    """Create the bucket if it doesn't exist."""
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        print(f"  Created bucket: {bucket}")
    else:
        print(f"  Bucket exists: {bucket}")


def sync_wiki_to_minio(dry_run: bool = False) -> dict:
    """
    Walk wiki/ directory and upload all .md files to MinIO.
    
    Returns stats dict with counts of uploaded, skipped, and failed files.
    """
    client = get_minio_client()
    ensure_bucket(client, MINIO_BUCKET)

    wiki_path = Path(WIKI_SOURCE_DIR)
    if not wiki_path.exists():
        print(f"ERROR: Wiki source directory not found: {wiki_path}")
        sys.exit(1)

    stats = {"uploaded": 0, "skipped": 0, "failed": 0, "total": 0}

    # Walk all .md files in wiki/
    md_files = sorted(wiki_path.rglob("*.md"))
    stats["total"] = len(md_files)

    print(f"\nFound {len(md_files)} markdown files in {wiki_path}")
    print(f"Target: MinIO bucket '{MINIO_BUCKET}' at {MINIO_ENDPOINT}\n")

    for md_file in md_files:
        # Object key = relative path from wiki/ using forward slashes
        relative_path = md_file.relative_to(wiki_path)
        object_key = relative_path.as_posix()

        if dry_run:
            print(f"  [DRY RUN] Would upload: {object_key}")
            stats["uploaded"] += 1
            continue

        try:
            # Check if object already exists and is up-to-date
            try:
                stat = client.stat_object(MINIO_BUCKET, object_key)
                local_mtime = md_file.stat().st_mtime
                remote_mtime = stat.last_modified.timestamp()
                if local_mtime <= remote_mtime:
                    # ponytail: mtime comparison; upgrade to etag/md5 if clock-skew hits
                    stats["skipped"] += 1
                    continue
            except S3Error:
                pass  # Object doesn't exist, upload it

            # Upload the file
            client.fput_object(
                MINIO_BUCKET,
                object_key,
                str(md_file),
                content_type="text/markdown",
            )
            print(f"  Uploaded: {object_key}")
            stats["uploaded"] += 1

        except S3Error as e:
            print(f"  FAILED: {object_key} — {e}")
            stats["failed"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Sync wiki/ to MinIO bucket")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without actually uploading",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  AI Runbook Assistant — Wiki -> MinIO Sync")
    print("=" * 60)

    stats = sync_wiki_to_minio(dry_run=args.dry_run)

    print(f"\n{'─' * 40}")
    print(f"  Total files:  {stats['total']}")
    print(f"  Uploaded:     {stats['uploaded']}")
    print(f"  Skipped:      {stats['skipped']} (unchanged)")
    print(f"  Failed:       {stats['failed']}")
    print(f"{'─' * 40}")

    if stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
