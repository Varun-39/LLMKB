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


# Low-value sections where LLM extraction is wasteful
_SKIP_EXTRACT_SECTIONS = {"links", "revision-history", "preamble", "revision-history-0"}
# Doc types where extraction is most valuable
_EXTRACT_DOC_TYPES = {"incident", "runbook"}


def _extract_llm_metadata(nodes: list) -> list:
    """
    Enrich nodes with LLM-generated keywords and a one-sentence summary.

    Applied only to incident/runbook nodes (where metadata varies most) and
    skips low-value sections. Uses the globally configured LLM (Ollama llama3.1).

    Adds to each qualifying node's metadata:
      - llm_keywords: comma-separated key terms extracted from the chunk
      - llm_summary: one-sentence summary of the chunk

    These are stored in ChromaDB metadata and can be used by retrieval signals.
    The extraction is best-effort — individual failures are logged and skipped.
    """
    from llama_index.core import Settings

    llm = Settings.llm
    eligible = [
        n for n in nodes
        if n.metadata.get("doc_type") in _EXTRACT_DOC_TYPES
        and n.metadata.get("section_name") not in _SKIP_EXTRACT_SECTIONS
    ]

    if not eligible:
        return nodes

    console.print(f"\n[bold blue]Step 3b:[/] LLM metadata extraction ({len(eligible)} nodes)...")
    console.print("  [dim](skipping templates, low-value sections, and non-incident/runbook types)[/]")

    for i, node in enumerate(eligible, 1):
        text = node.get_content()[:2000]  # cap to avoid huge prompts
        doc_id = node.metadata.get("id", "?")
        section = node.metadata.get("section_name", "?")

        prompt = (
            f"Extract the 5 most important technical keywords from this SRE document section "
            f"and write a one-sentence summary. Return ONLY:\n"
            f"KEYWORDS: <comma-separated keywords>\n"
            f"SUMMARY: <one sentence>\n\n"
            f"Text:\n{text}"
        )

        try:
            response = str(llm.complete(prompt)).strip()
            keywords = ""
            summary = ""

            for line in response.splitlines():
                if line.upper().startswith("KEYWORDS:"):
                    keywords = line.split(":", 1)[1].strip()
                elif line.upper().startswith("SUMMARY:"):
                    summary = line.split(":", 1)[1].strip()

            if keywords:
                node.metadata["llm_keywords"] = keywords[:500]  # ChromaDB metadata limit
                node.excluded_llm_metadata_keys = list(node.excluded_llm_metadata_keys or [])
                if "llm_keywords" not in node.excluded_embed_metadata_keys:
                    # Include in embeddings — this is the point
                    pass

            if summary:
                node.metadata["llm_summary"] = summary[:500]

            console.print(f"  [{i}/{len(eligible)}] {doc_id}::{section} → {len(keywords.split(',')) if keywords else 0} keywords")

        except Exception as e:
            console.print(f"  [{i}/{len(eligible)}] {doc_id}::{section} → [yellow]SKIP: {e}[/]")

    return nodes


def run_ingestion(
    force: bool = False,
    local: bool = False,
    prefix: str | None = None,
    extract_metadata: bool = False,
) -> dict:
    """
    Run the full ingestion pipeline using LlamaIndex.

    Args:
        force: If True, re-index everything regardless of manifest state
        local: If True, load from local wiki/ instead of MinIO
        prefix: Optional MinIO prefix filter (e.g., "Incidents/")
        extract_metadata: If True, run LLM-powered keyword/summary extraction
                          per chunk (slow — adds ~1-3s per node via Ollama).
                          Applied only to incident and runbook nodes to limit cost.

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

    # --- Step 4b (optional): LLM metadata extraction ---
    if extract_metadata:
        all_nodes = _extract_llm_metadata(all_nodes)

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
    parser.add_argument("--extract-metadata", action="store_true",
                        help="LLM-powered keyword/summary extraction per chunk (slow, ~1-3s/node)")
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
        extract_metadata=args.extract_metadata,
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
