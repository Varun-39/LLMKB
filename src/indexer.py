"""
LlamaIndex ChromaDB Indexer — builds and manages the VectorStoreIndex
backed by a persistent ChromaDB collection.

Provides:
- Index construction from LlamaIndex Documents
- Incremental node insertion (for delta updates)
- Index loading from existing ChromaDB persistence
- Collection reset and stats
"""

import chromadb
from chromadb.config import Settings as ChromaSettings

from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.schema import BaseNode
from llama_index.vector_stores.chroma import ChromaVectorStore

from src.config import CHROMA_PERSIST_DIR, CHROMA_COLLECTION


def get_chroma_client() -> chromadb.PersistentClient:
    """Get or create a persistent ChromaDB client."""
    return chromadb.PersistentClient(
        path=CHROMA_PERSIST_DIR,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_chroma_collection():
    """Get or create the ChromaDB collection."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def get_vector_store() -> ChromaVectorStore:
    """Create a LlamaIndex ChromaVectorStore wrapping our persistent collection."""
    chroma_collection = get_chroma_collection()
    return ChromaVectorStore(chroma_collection=chroma_collection)


def get_storage_context() -> StorageContext:
    """Create a StorageContext with ChromaDB as the vector store."""
    vector_store = get_vector_store()
    return StorageContext.from_defaults(vector_store=vector_store)


def build_index_from_documents(documents: list, node_parser=None) -> VectorStoreIndex:
    """
    Build a VectorStoreIndex from a list of LlamaIndex Documents.

    This embeds all documents (via the configured node_parser and embed model)
    and stores them in ChromaDB.

    Args:
        documents: List of LlamaIndex Document objects
        node_parser: Optional custom NodeParser (defaults to SectionNodeParser)

    Returns:
        VectorStoreIndex instance
    """
    from src.chunker import SectionNodeParser

    if node_parser is None:
        node_parser = SectionNodeParser()

    storage_context = get_storage_context()

    # Build index — this handles parsing, embedding, and storage
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        transformations=[node_parser],
        show_progress=True,
    )

    return index


def insert_nodes(nodes: list[BaseNode]) -> int:
    """
    Insert pre-parsed nodes into the existing ChromaDB-backed index.

    Used for incremental/delta updates where documents have already
    been parsed into TextNodes by SectionNodeParser.

    Args:
        nodes: List of TextNode objects to embed and store

    Returns:
        Number of nodes inserted
    """
    storage_context = get_storage_context()

    # Load existing index
    index = VectorStoreIndex.from_vector_store(
        vector_store=storage_context.vector_store,
        storage_context=storage_context,
    )

    # Insert new nodes
    index.insert_nodes(nodes)

    return len(nodes)


def load_index() -> VectorStoreIndex:
    """
    Load the existing VectorStoreIndex from ChromaDB persistence.

    Use this at query time — no embedding happens, just connects
    to the existing vector store.

    Returns:
        VectorStoreIndex backed by existing ChromaDB data
    """
    storage_context = get_storage_context()

    return VectorStoreIndex.from_vector_store(
        vector_store=storage_context.vector_store,
        storage_context=storage_context,
    )


def delete_nodes_by_doc(doc_id: str, object_key: str | None = None) -> int:
    """
    Delete all nodes belonging to a specific document from ChromaDB.

    Args:
        doc_id: The human-facing document ID from metadata.
        object_key: The unique source path, used as the preferred delete key.

    Returns:
        Count of deleted nodes
    """
    collection = get_chroma_collection()

    if object_key:
        results = collection.get(where={"object_key": object_key})

        if results["ids"]:
            collection.delete(ids=results["ids"])
            return len(results["ids"])

    if not object_key:
        results = collection.get(where={"id": doc_id})

        if results["ids"]:
            collection.delete(ids=results["ids"])
            return len(results["ids"])

    # Also try prefix-based deletion for legacy or partially indexed chunks.
    # ChromaDB doesn't support prefix queries in where, so get all and filter
    all_results = collection.get(limit=10000)
    prefixes = [f"{object_key}::"] if object_key else [f"{doc_id}::"]

    ids_to_delete = [
        nid for nid in all_results["ids"]
        if any(nid.startswith(prefix) for prefix in prefixes)
    ]

    if ids_to_delete:
        collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)

    return 0


def reset_index() -> None:
    """Delete the entire collection and start fresh."""
    client = get_chroma_client()
    try:
        client.delete_collection(CHROMA_COLLECTION)
        print(f"  Collection '{CHROMA_COLLECTION}' deleted.")
    except Exception:
        print(f"  Collection '{CHROMA_COLLECTION}' does not exist (nothing to delete).")


def get_collection_stats() -> dict:
    """Get basic stats about the indexed collection."""
    try:
        collection = get_chroma_collection()
        return {
            "collection": CHROMA_COLLECTION,
            "total_chunks": collection.count(),
        }
    except Exception as e:
        return {"error": str(e)}
