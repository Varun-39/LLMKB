"""
Lightweight Service Dependency Graph — extracts and queries
service relationships from LLMKB2 incident data.

This is a simplified property graph implementation that works with
the existing ChromaDB index without requiring Neo4j/Memgraph.
It builds an in-memory graph of service dependencies, incident
relationships, and blast-radius analysis from document metadata.

Capabilities:
  - Build service dependency graph from incident/system docs
  - Answer "What services are affected if X goes down?"
  - Answer "Show me all incidents related to service X"
  - Cross-incident relationship analysis

Usage:
    from src.graph import ServiceGraph
    graph = ServiceGraph()
    graph.build()
    graph.affected_by("postgres-primary")
    graph.incidents_for("payment-gateway")
"""

import re
from collections import defaultdict
from typing import Optional

from src.indexer import get_chroma_collection
from src.retrieval import CONFIG

KNOWN_SERVICES = set(CONFIG.get("known_services", []))


class ServiceNode:
    """A service/infrastructure component in the graph."""

    def __init__(self, name: str, node_type: str = "service"):
        self.name = name
        self.node_type = node_type  # service, database, node, infrastructure
        self.incidents: list[str] = []  # incident IDs
        self.runbooks: list[str] = []  # runbook IDs
        self.properties: dict = {}

    def __repr__(self):
        return f"ServiceNode({self.name}, incidents={len(self.incidents)}, runbooks={len(self.runbooks)})"


class Edge:
    """A relationship between two nodes."""

    def __init__(self, source: str, target: str, relation: str, weight: float = 1.0):
        self.source = source
        self.target = target
        self.relation = relation  # depends_on, affected_by, related_to, co_occurs
        self.weight = weight
        self.evidence: list[str] = []  # doc IDs that support this relationship

    def __repr__(self):
        return f"Edge({self.source} --[{self.relation}]--> {self.target})"


class ServiceGraph:
    """
    In-memory property graph of service dependencies and incident relationships.

    Built from ChromaDB metadata and document content without requiring
    an external graph database. Enables blast-radius analysis and
    cross-incident relationship queries.
    """

    def __init__(self):
        self.nodes: dict[str, ServiceNode] = {}
        self.edges: list[Edge] = []
        self._adjacency: dict[str, list[Edge]] = defaultdict(list)
        self._reverse_adjacency: dict[str, list[Edge]] = defaultdict(list)
        self._built = False

    def _get_or_create_node(self, name: str, node_type: str = "service") -> ServiceNode:
        """Get existing node or create a new one."""
        name_lower = name.lower()
        if name_lower not in self.nodes:
            self.nodes[name_lower] = ServiceNode(name_lower, node_type)
        return self.nodes[name_lower]

    def _add_edge(self, source: str, target: str, relation: str, doc_id: str = "", weight: float = 1.0):
        """Add a directed edge between two nodes."""
        source_lower = source.lower()
        target_lower = target.lower()
        if source_lower == target_lower:
            return

        # Check for duplicate
        for edge in self._adjacency[source_lower]:
            if edge.target == target_lower and edge.relation == relation:
                edge.weight += 0.5  # strengthen existing edge
                if doc_id and doc_id not in edge.evidence:
                    edge.evidence.append(doc_id)
                return

        edge = Edge(source_lower, target_lower, relation, weight)
        if doc_id:
            edge.evidence.append(doc_id)
        self.edges.append(edge)
        self._adjacency[source_lower].append(edge)
        self._reverse_adjacency[target_lower].append(edge)

    def _extract_services_from_text(self, text: str) -> set[str]:
        """Extract service mentions from document text."""
        found = set()
        text_lower = text.lower()
        for svc in KNOWN_SERVICES:
            if svc in ("general", "all"):
                continue
            # Match full service name or key parts
            if svc in text_lower:
                found.add(svc)
            else:
                # Try matching key parts (e.g., "payment" from "payment-gateway")
                parts = [p for p in svc.split("-") if p not in ("service", "gateway")]
                if any(p in text_lower for p in parts if len(p) > 3):
                    found.add(svc)
        return found

    def _extract_infra_components(self, text: str) -> set[str]:
        """Extract infrastructure component mentions (databases, nodes, etc.)."""
        components = set()
        text_lower = text.lower()

        # Common infrastructure patterns
        patterns = [
            (r"(?:postgres|postgresql|mysql|redis|mongo|elasticsearch|kafka)\S*", "database"),
            (r"node-?\d+|worker-?\d+|master-?\d+", "node"),
            (r"(?:k8s|kubernetes)\s+(?:cluster|node|pod)", "infrastructure"),
        ]

        for pattern, _ in patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                components.add(match.strip())

        return components

    def build(self):
        """Build the service graph from ChromaDB metadata and document content."""
        collection = get_chroma_collection()
        total = collection.count()
        results = collection.get(limit=max(total, 1), include=["documents", "metadatas"])

        node_ids = results.get("ids") or []
        texts = results.get("documents") or []
        metadatas = results.get("metadatas") or []

        # Phase 1: Build nodes from metadata
        doc_services: dict[str, set[str]] = defaultdict(set)  # doc_id -> services mentioned

        for i, node_id in enumerate(node_ids):
            meta = metadatas[i] if i < len(metadatas) else {}
            text = texts[i] if i < len(texts) else ""
            doc_id = meta.get("id", "")
            doc_type = meta.get("doc_type", "")
            primary_service = meta.get("service", "")

            if not doc_id:
                continue

            # Create node for primary service
            if primary_service and primary_service not in ("general", "all"):
                node = self._get_or_create_node(primary_service)
                if doc_type == "incident" and doc_id not in node.incidents:
                    node.incidents.append(doc_id)
                elif doc_type == "runbook" and doc_id not in node.runbooks:
                    node.runbooks.append(doc_id)

            # Extract other services mentioned in the text
            mentioned_services = self._extract_services_from_text(text)
            doc_services[doc_id].update(mentioned_services)
            if primary_service:
                doc_services[doc_id].add(primary_service)

        # Phase 2: Build edges from co-occurrence
        for doc_id, services in doc_services.items():
            services_list = sorted(services - {"general", "all"})
            if len(services_list) < 2:
                continue

            # Primary service (first one) has edges to all others
            primary = services_list[0]
            for other in services_list[1:]:
                self._add_edge(primary, other, "related_to", doc_id)
                self._add_edge(other, primary, "related_to", doc_id)

        # Phase 3: Extract infrastructure dependencies from system docs
        for i, node_id in enumerate(node_ids):
            meta = metadatas[i] if i < len(metadatas) else {}
            text = texts[i] if i < len(texts) else ""
            doc_type = meta.get("doc_type", "")
            doc_id = meta.get("id", "")
            service = meta.get("service", "")

            if doc_type != "system" or not service:
                continue

            # Look for dependency keywords
            text_lower = text.lower()
            dep_patterns = [
                r"depends?\s+on\s+(\S+)",
                r"connects?\s+to\s+(\S+)",
                r"backed\s+by\s+(\S+)",
                r"uses?\s+(\S+)\s+(?:database|db|store|queue|cache)",
            ]

            for pattern in dep_patterns:
                matches = re.findall(pattern, text_lower)
                for target in matches:
                    target_clean = target.strip(".,;:")
                    if len(target_clean) > 2:
                        self._add_edge(service, target_clean, "depends_on", doc_id)

        self._built = True

    def affected_by(self, service: str, depth: int = 2) -> dict[str, list[str]]:
        """
        Find services affected if the given service goes down (blast radius).

        Returns dict of {service_name: [evidence_doc_ids]} at each depth level.
        """
        if not self._built:
            self.build()

        service = service.lower()
        visited = set()
        affected = {}

        # BFS traversal
        queue = [(service, 0)]
        while queue:
            current, current_depth = queue.pop(0)
            if current in visited or current_depth > depth:
                continue
            visited.add(current)

            for edge in self._reverse_adjacency.get(current, []):
                if edge.source not in visited:
                    affected[edge.source] = edge.evidence
                    queue.append((edge.source, current_depth + 1))

            for edge in self._adjacency.get(current, []):
                if edge.target not in visited and edge.relation in ("depends_on", "related_to"):
                    affected[edge.target] = edge.evidence
                    queue.append((edge.target, current_depth + 1))

        return affected

    def incidents_for(self, service: str) -> list[str]:
        """Get all incident IDs associated with a service."""
        if not self._built:
            self.build()

        service = service.lower()
        node = self.nodes.get(service)
        if node:
            return node.incidents
        return []

    def runbooks_for(self, service: str) -> list[str]:
        """Get all runbook IDs associated with a service."""
        if not self._built:
            self.build()

        service = service.lower()
        node = self.nodes.get(service)
        if node:
            return node.runbooks
        return []

    def get_stats(self) -> dict:
        """Get summary statistics about the graph."""
        if not self._built:
            self.build()

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "services": [n.name for n in self.nodes.values() if n.node_type == "service"],
            "relationship_types": list(set(e.relation for e in self.edges)),
            "nodes_with_incidents": sum(1 for n in self.nodes.values() if n.incidents),
            "nodes_with_runbooks": sum(1 for n in self.nodes.values() if n.runbooks),
        }

    def describe(self) -> str:
        """Human-readable description of the graph."""
        stats = self.get_stats()
        lines = [
            f"Service Graph: {stats['total_nodes']} nodes, {stats['total_edges']} edges",
            f"Services: {', '.join(stats['services'])}",
            f"Relationship types: {', '.join(stats['relationship_types'])}",
            "",
            "Edges:",
        ]
        for edge in sorted(self.edges, key=lambda e: (e.source, e.relation)):
            lines.append(f"  {edge.source} --[{edge.relation}]--> {edge.target} (evidence: {', '.join(edge.evidence[:3])})")
        return "\n".join(lines)


# Module-level cached graph
_graph: Optional[ServiceGraph] = None


def get_service_graph() -> ServiceGraph:
    """Get or build the service dependency graph."""
    global _graph
    if _graph is None:
        _graph = ServiceGraph()
        _graph.build()
    return _graph


def reset_graph():
    """Reset the graph (call after re-ingestion)."""
    global _graph
    _graph = None
