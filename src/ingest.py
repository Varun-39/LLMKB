"""
LlamaIndex Ingestion Pipeline — orchestrates the full flow:
  MinIO (or local) -> Load -> Parse (section nodes) -> Embed -> Index (ChromaDB)

Supports:
- Full re-index (--force flag)
- Delta re-index (only changed files, using manifest)
- Local mode (--local flag, bypasses MinIO)

Usage:
    python -m src.ingest
    python -m src.ingest --force
    python -m src.ingest --local
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
from rich.console import Console
from rich.table import Table

from src.config import init_llama_index_settings
from src.loader import LocalMarkdownReader, MinIOMarkdownReader
from src.chunker import SectionNodeParser
from src.indexer import (
    build_index_from_documents,
    insert_nodes,
    reset_index,
    get_collection_stats,
    delete_nodes_by_doc,
)
from src.manifest import (
    is_changed,
    record_indexed,
    get_all_indexed_keys,
    remove_from_manifest,
    get_manifest_stats,
    reset_manifest,
)

console = Console()


def run_ingestion(
    force: bool = False,
    local: bool = False,
    prefix: str | None = None,
) -> dict:
    """
    Run the full ingestion pipeline using LlamaIndex.

    Args:
        force: If True, re-index everything regardless of manifest state
        local: If True, load from local wiki/ instead of MinIO
        prefix: Optional MinIO prefix filter (e.g., "Incidents/")

    Returns:
        Stats dict
    """
    stats = {
        "docs_loaded": 0,
        "docs_changed": 0,
        "docs_skipped": 0,
        "nodes_created": 0,
        "nodes_indexed": 0,
    }

    # --- Step 1: Load documents using LlamaIndex readers ---
    console.print("\n[bold blue]Step 1:[/] Loading documents...")

    if local:
        reader = LocalMarkdownReader()
        documents = reader.load_data()
        console.print(f"  Loaded {len(documents)} documents from local wiki/")
    else:
        reader = MinIOMarkdownReader(prefix=prefix)
        documents = reader.load_data()
        console.print(f"  Loaded {len(documents)} documents from MinIO")

    stats["docs_loaded"] = len(documents)

    if not documents:
        console.print("[yellow]  No documents found. Nothing to index.[/]")
        return stats

    # --- Step 2: If force, reset index and manifest ---
    if force:
        console.print("\n[bold yellow]  --force flag: resetting index and manifest[/]")
        reset_index()
        reset_manifest()

    # --- Step 3: Filter to changed documents only ---
    console.print("\n[bold blue]Step 2:[/] Checking for changes...")

    docs_to_process = []
    for doc in documents:
        object_key = doc.metadata.get("object_key", doc.doc_id)
        if force or is_changed(object_key, doc.text):
            docs_to_process.append(doc)
        else:
            stats["docs_skipped"] += 1

    stats["docs_changed"] = len(docs_to_process)
    console.print(f"  Changed: {len(docs_to_process)} | Skipped: {stats['docs_skipped']}")

    if not docs_to_process:
        console.print("[green]  All documents up to date. Nothing to do.[/]")
        return stats

    # --- Step 4: Parse documents into section-level nodes ---
    console.print("\n[bold blue]Step 3:[/] Parsing documents into section nodes...")

    node_parser = SectionNodeParser()
    all_nodes = node_parser.get_nodes_from_documents(docs_to_process)

    stats["nodes_created"] = len(all_nodes)
    console.print(f"  Total nodes created: {len(all_nodes)}")

    # Show per-document breakdown
    for doc in docs_to_process:
        doc_id = doc.metadata.get("id", doc.doc_id)
        doc_nodes = [n for n in all_nodes if n.metadata.get("id") == doc_id]
        console.print(f"  {doc.metadata.get('object_key', doc_id)} -> {len(doc_nodes)} nodes")

    # --- Step 5: Delete old nodes for changed docs (delta mode) ---
    if not force:
        console.print("\n[bold blue]Step 4:[/] Removing old nodes for changed documents...")
        for doc in docs_to_process:
            doc_id = doc.metadata.get("id", doc.doc_id)
            object_key = doc.metadata.get("object_key", doc.doc_id)
            deleted = delete_nodes_by_doc(doc_id, object_key=object_key)
            if deleted > 0:
                console.print(f"    Deleted {deleted} old nodes for {object_key}")

    # --- Step 6: Embed and index nodes ---
    console.print("\n[bold blue]Step 5:[/] Embedding and indexing into ChromaDB via LlamaIndex...")

    if force:
        # Full rebuild — use from_documents which handles everything
        index = build_index_from_documents(docs_to_process, node_parser=node_parser)
        stats["nodes_indexed"] = len(all_nodes)
    else:
        # Incremental — insert pre-parsed nodes
        count = insert_nodes(all_nodes)
        stats["nodes_indexed"] = count

    console.print(f"  Indexed: {stats['nodes_indexed']} nodes")

    # --- Step 7: Update manifest ---
    console.print("\n[bold blue]Step 6:[/] Updating manifest...")

    for doc in docs_to_process:
        object_key = doc.metadata.get("object_key", doc.doc_id)
        doc_id = doc.metadata.get("id", doc.doc_id)
        doc_nodes = [n for n in all_nodes if n.metadata.get("id") == doc_id]
        record_indexed(
            object_key=object_key,
            content=doc.text,
            chunk_count=len(doc_nodes),
            doc_type=doc.metadata.get("doc_type", ""),
        )

    # --- Step 8: Handle deletions ---
    current_keys = {doc.metadata.get("object_key", doc.doc_id) for doc in documents}
    manifest_keys = get_all_indexed_keys()
    deleted_keys = manifest_keys - current_keys

    if deleted_keys:
        console.print(f"\n  Removing {len(deleted_keys)} deleted documents from manifest...")
        for key in deleted_keys:
            remove_from_manifest(key)

    return stats


def print_summary(stats: dict) -> None:
    """Print a rich summary table."""
    table = Table(title="Ingestion Summary (LlamaIndex)")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Documents loaded", str(stats["docs_loaded"]))
    table.add_row("Documents changed", str(stats["docs_changed"]))
    table.add_row("Documents skipped", str(stats["docs_skipped"]))
    table.add_row("Nodes created", str(stats["nodes_created"]))
    table.add_row("Nodes indexed", str(stats["nodes_indexed"]))

    console.print(table)

    # Collection stats
    coll_stats = get_collection_stats()
    if "total_chunks" in coll_stats:
        console.print(f"\n  ChromaDB total nodes: {coll_stats['total_chunks']}")

    manifest_stats = get_manifest_stats()
    console.print(f"  Manifest total docs:  {manifest_stats['total_documents']}")
    if manifest_stats["by_type"]:
        for doc_type, count in manifest_stats["by_type"].items():
            console.print(f"    {doc_type}: {count}")


def main():
    parser = argparse.ArgumentParser(description="LLMKB2 Ingestion Pipeline (LlamaIndex)")
    parser.add_argument("--force", action="store_true",
                        help="Force full re-index (ignore manifest)")
    parser.add_argument("--local", action="store_true",
                        help="Load from local wiki/ instead of MinIO")
    parser.add_argument("--prefix", type=str, default=None,
                        help="MinIO prefix filter (e.g., 'Incidents/')")
    args = parser.parse_args()

    # Initialize LlamaIndex with configured LLM/embedding models
    init_llama_index_settings()

    console.print("=" * 60)
    console.print("  [bold]LLMKB2 — Ingestion Pipeline (LlamaIndex)[/]")
    console.print("=" * 60)

    import time
    t0 = time.perf_counter()

    stats = run_ingestion(
        force=args.force,
        local=args.local,
        prefix=args.prefix,
    )

    elapsed = time.perf_counter() - t0

    print_summary(stats)
    console.print(f"\n[bold green]Done.[/] Total time: {elapsed:.1f}s\n")
    # ponytail: ChromaDB PersistentClient keeps background threads alive; force-exit
    # to avoid hanging. Upgrade path: switch to ephemeral client or use context manager
    # if chromadb ever exposes a clean shutdown API.
    raise SystemExit(0)


if __name__ == "__main__":
    main()
