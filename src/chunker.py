"""
LlamaIndex Section Node Parser — splits documents at ## boundaries
with Contextual Retrieval augmentation (Anthropic-style).

Implements the same section-level chunking philosophy as before:
- Never split within a section
- Each node preserves full section content (code blocks, tables, sub-lists)
- Inherits parent document metadata + adds section-specific metadata
- NEW: Prepends a contextual blurb to each chunk for better embeddings

The contextual blurb ensures the embedding captures document-level context
(doc ID, type, service, section purpose) that raw section text alone misses.

Wraps the custom logic as a LlamaIndex NodeParser for pipeline integration.
"""

import re
from typing import Any, Sequence

from llama_index.core.node_parser import NodeParser
from llama_index.core.schema import BaseNode, TextNode


# --- Contextual Retrieval ---

# Readable labels for doc types
_DOC_TYPE_LABELS = {
    "incident": "incident report",
    "runbook": "operational runbook",
    "system": "system architecture document",
    "governance": "governance policy",
    "vendor-note": "vendor advisory",
    "template": "template",
    "unknown": "document",
}

# Readable labels for section types — helps the embedding understand section purpose
_SECTION_LABELS = {
    "summary": "a summary of the event",
    "incident-summary": "a summary of the incident",
    "timeline": "a chronological timeline of events",
    "diagnosis": "diagnostic steps and root cause analysis",
    "symptoms": "observed symptoms and alert patterns",
    "resolution": "resolution steps and commands used to fix the issue",
    "mitigation": "mitigation actions taken to reduce impact",
    "mitigation-option-a": "a mitigation option",
    "mitigation-option-b": "an alternative mitigation option",
    "fix": "the fix applied to resolve the issue",
    "triage": "triage steps for initial investigation",
    "post-incident-review": "a post-incident review of what happened and lessons learned",
    "action-items": "follow-up action items from the incident",
    "links": "reference links and related documents",
    "revision-history": "document revision history",
    "preamble": "introductory context",
}


def build_context_prefix(metadata: dict, section_name: str) -> str:
    """
    Build a short contextual blurb that situates a chunk within its parent document.

    This is prepended to the chunk text before embedding (Anthropic-style contextual
    retrieval). The embedding model then captures both the local content AND the
    document-level context, dramatically improving retrieval for queries that
    don't use the exact same terminology as the chunk.

    Example output:
      "This is the 'Resolution' section (resolution steps and commands used to fix
       the issue) from incident report INC-001, related to payment-gateway service."
    """
    doc_id = metadata.get("id", "")
    doc_type = metadata.get("doc_type", "unknown")
    service = metadata.get("service", "general")
    title = metadata.get("title", "")

    doc_type_label = _DOC_TYPE_LABELS.get(doc_type, doc_type)
    section_label = _SECTION_LABELS.get(section_name, "")

    parts = []
    parts.append(f"This is the '{section_name}' section")
    if section_label:
        parts[0] += f" ({section_label})"

    # Source document context
    source_parts = []
    if doc_type_label:
        source_parts.append(doc_type_label)
    if doc_id:
        source_parts.append(doc_id)
    if source_parts:
        parts.append(f"from {' '.join(source_parts)}")

    if title and title != doc_id:
        parts.append(f"titled '{title}'")

    if service and service not in ("general", "all"):
        parts.append(f"related to {service} service")

    return ", ".join(parts) + "."


def normalize_section_name(header: str) -> str:
    """
    Convert a markdown header to a normalized section identifier.
    "## Post-Incident Review" -> "post-incident-review"
    """
    name = re.sub(r"^#+\s*", "", header).strip()
    name = re.sub(r"[^a-z0-9]+", "-", name.lower())
    name = name.strip("-")
    return name


def split_by_sections(content: str) -> list[tuple[str, str]]:
    """
    Split markdown content at ## boundaries.
    Returns list of (header_text, section_body) tuples.
    """
    pattern = r"^(## .+)$"

    sections = []
    lines = content.split("\n")

    current_header = ""
    current_lines = []

    for line in lines:
        if re.match(pattern, line):
            if current_lines or current_header:
                body = "\n".join(current_lines).strip()
                if body:
                    sections.append((current_header, body))
            current_header = line.strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_header, body))

    return sections


def make_chunk_id(metadata: dict, fallback_id: str, section_name: str, used_ids: set[str]) -> str:
    """
    Build a ChromaDB node ID from the source object key.

    Frontmatter IDs are human-facing and can occasionally be reused across files.
    The object_key is the unique storage path, so it is the stable vector ID prefix.
    """
    doc_key = str(metadata.get("object_key") or metadata.get("id") or fallback_id)
    base_id = f"{doc_key}::{section_name}"
    chunk_id = base_id
    suffix = 1

    while chunk_id in used_ids:
        suffix += 1
        chunk_id = f"{base_id}-{suffix}"

    used_ids.add(chunk_id)
    return chunk_id


class SectionNodeParser(NodeParser):
    """
    Custom LlamaIndex NodeParser that splits documents at ## header boundaries
    with Contextual Retrieval augmentation.

    Each resulting TextNode contains:
    - A contextual blurb (doc ID, type, service, section purpose)
    - The full section text (header + body)
    - All parent document metadata
    - section_name, section_index, section_header as extra metadata
    """

    def _parse_nodes(
        self,
        nodes: Sequence[BaseNode],
        show_progress: bool = False,
        **kwargs: Any,
    ) -> list[BaseNode]:
        """Parse documents/nodes into section-level TextNodes with contextual augmentation."""
        all_nodes = []
        used_ids = set()

        for node in nodes:
            text = node.get_content()
            metadata = node.metadata.copy() if node.metadata else {}

            sections = split_by_sections(text)

            if not sections and text.strip():
                # No ## headers — treat entire doc as one node
                chunk_id = make_chunk_id(metadata, node.node_id, "full", used_ids)

                section_metadata = dict(metadata)
                section_metadata["section_name"] = "full"
                section_metadata["section_index"] = 0
                section_metadata["section_header"] = ""
                section_metadata["chunk_id"] = chunk_id

                # Contextual augmentation for full-doc nodes
                context_prefix = build_context_prefix(metadata, "full")
                augmented_text = f"{context_prefix}\n\n{text}"

                text_node = TextNode(
                    text=augmented_text,
                    metadata=section_metadata,
                    id_=chunk_id,
                )
                # Exclude section fields from embedding to avoid noise
                text_node.excluded_llm_metadata_keys = ["section_index", "section_header", "object_key", "chunk_id"]
                text_node.excluded_embed_metadata_keys = ["section_index", "section_header", "object_key", "chunk_id"]
                all_nodes.append(text_node)
                continue

            for idx, (header, body) in enumerate(sections):
                section_name = normalize_section_name(header) if header else "preamble"
                chunk_id = make_chunk_id(metadata, node.node_id, section_name, used_ids)

                # Build the contextual prefix
                context_prefix = build_context_prefix(metadata, section_name)

                # Include header in content for retrieval context
                if header:
                    chunk_content = f"{context_prefix}\n\n{header}\n\n{body}"
                else:
                    chunk_content = f"{context_prefix}\n\n{body}"

                section_metadata = dict(metadata)
                section_metadata["section_name"] = section_name
                section_metadata["section_index"] = idx
                section_metadata["section_header"] = header
                section_metadata["chunk_id"] = chunk_id

                text_node = TextNode(
                    text=chunk_content,
                    metadata=section_metadata,
                    id_=chunk_id,
                )
                text_node.excluded_llm_metadata_keys = ["section_index", "section_header", "object_key", "chunk_id"]
                text_node.excluded_embed_metadata_keys = ["section_index", "section_header", "object_key", "chunk_id"]
                all_nodes.append(text_node)

        return all_nodes

    @classmethod
    def class_name(cls) -> str:
        return "SectionNodeParser"
