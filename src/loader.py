"""
LlamaIndex Document Reader — loads markdown files from MinIO or local wiki/,
extracts YAML frontmatter, infers doc_type, and returns LlamaIndex Document objects.

Implements llama_index BaseReader interface for seamless pipeline integration.
"""

from pathlib import Path
from typing import Optional

import yaml
from llama_index.core import Document as LIDocument
from llama_index.core.readers.base import BaseReader

from src.config import (
    MINIO_ENDPOINT,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    MINIO_BUCKET,
    MINIO_SECURE,
    WIKI_SOURCE_DIR,
    DOC_TYPE_MAP,
)


def infer_doc_type(object_key: str) -> str:
    """
    Infer document type from path prefix.
    E.g., "Incidents/INC-001-..." -> "incident"
    """
    parts = object_key.split("/")
    if len(parts) >= 2:
        folder = parts[0]
        return DOC_TYPE_MAP.get(folder, "unknown")
    return "unknown"


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Extract YAML frontmatter from markdown content.
    Returns (metadata_dict, body_without_frontmatter).
    """
    if not content.startswith("---"):
        return {}, content

    end_index = content.find("---", 3)
    if end_index == -1:
        return {}, content

    frontmatter_str = content[3:end_index].strip()
    body = content[end_index + 3:].strip()

    try:
        metadata = yaml.safe_load(frontmatter_str)
        if not isinstance(metadata, dict):
            metadata = {}
    except yaml.YAMLError:
        metadata = {}

    return metadata, body


def normalize_metadata(raw_metadata: dict, object_key: str) -> dict:
    """
    Normalize and enrich metadata for consistent retrieval filtering.
    All values are str/int/float/bool for ChromaDB compatibility.
    """
    normalized = {}

    # Core identifiers
    normalized["doc_type"] = infer_doc_type(object_key)
    normalized["id"] = str(raw_metadata.get("id", object_key))
    normalized["title"] = raw_metadata.get("title", object_key.split("/")[-1].replace(".md", ""))
    normalized["object_key"] = object_key

    # Service
    service = raw_metadata.get("service", "general")
    if service == "*":
        service = "all"
    normalized["service"] = str(service).lower()

    # Severity
    normalized["severity"] = raw_metadata.get("severity", "").upper() if raw_metadata.get("severity") else ""

    # Environment
    normalized["environment"] = raw_metadata.get("environment", "prod")

    # Category
    normalized["category"] = raw_metadata.get("category", "")

    # Tags (flatten to comma-separated string)
    tags = raw_metadata.get("tags", [])
    if isinstance(tags, list):
        normalized["tags"] = ",".join(str(t) for t in tags)
    else:
        normalized["tags"] = str(tags) if tags else ""

    # Duration
    if "duration" in raw_metadata:
        normalized["duration"] = str(raw_metadata["duration"])

    # Risk level
    if "risk_level" in raw_metadata:
        normalized["risk_level"] = raw_metadata["risk_level"]

    # Date
    if "date" in raw_metadata:
        normalized["date"] = str(raw_metadata["date"])

    return normalized


class MinIOMarkdownReader(BaseReader):
    """
    LlamaIndex reader that loads markdown documents from MinIO.
    Parses YAML frontmatter and normalizes metadata.
    """

    def __init__(
        self,
        prefix: Optional[str] = None,
        exclude_templates: bool = True,
    ):
        self.prefix = prefix
        self.exclude_templates = exclude_templates

    def load_data(self) -> list[LIDocument]:
        from minio import Minio
        from minio.error import S3Error

        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )

        documents = []
        objects = client.list_objects(MINIO_BUCKET, prefix=self.prefix, recursive=True)

        for obj in objects:
            key = obj.object_name

            if not key.endswith(".md"):
                continue
            if self.exclude_templates and key.startswith("Templates/"):
                continue
            if ".obsidian" in key:
                continue

            try:
                response = client.get_object(MINIO_BUCKET, key)
                raw_content = response.read().decode("utf-8")
                response.close()
                response.release_conn()

                raw_metadata, body = parse_frontmatter(raw_content)
                metadata = normalize_metadata(raw_metadata, key)

                documents.append(LIDocument(
                    text=body,
                    metadata=metadata,
                    doc_id=metadata["id"],
                ))

            except S3Error as e:
                print(f"  WARNING: Failed to load {key}: {e}")
                continue

        return documents


class LocalMarkdownReader(BaseReader):
    """
    LlamaIndex reader that loads markdown documents from local wiki/ directory.
    Useful for development/testing without MinIO running.
    """

    def __init__(
        self,
        wiki_dir: Optional[str] = None,
        exclude_templates: bool = True,
    ):
        self.wiki_path = Path(wiki_dir or WIKI_SOURCE_DIR)
        self.exclude_templates = exclude_templates

    def load_data(self) -> list[LIDocument]:
        documents = []

        for md_file in sorted(self.wiki_path.rglob("*.md")):
            relative_path = md_file.relative_to(self.wiki_path)
            object_key = relative_path.as_posix()

            if self.exclude_templates and object_key.startswith("Templates/"):
                continue
            if ".obsidian" in object_key:
                continue

            raw_content = md_file.read_text(encoding="utf-8")
            raw_metadata, body = parse_frontmatter(raw_content)
            metadata = normalize_metadata(raw_metadata, object_key)

            documents.append(LIDocument(
                text=body,
                metadata=metadata,
                doc_id=metadata["id"],
            ))

        return documents
