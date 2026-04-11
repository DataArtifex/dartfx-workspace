"""
RDF Knowledge Base interactions using rdflib.
"""

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, XSD

DARTFX = Namespace("https://dataartifex.org/workspace/")
SCHEMA = Namespace("https://schema.org/")


class KnowledgeBase:
    """
    Manages workspace knowledge base and state persistence using an RDF Graph.
    """

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.kb_dir = self.workspace_path / ".dartfx" / "kb"
        self.resource_dir = self.kb_dir / "workspace"
        self.graph = Graph()
        self.resource_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        """Loads all individual turtle files from the resource directory."""
        self.graph.bind("dcterms", DCTERMS)
        self.graph.bind("schema", SCHEMA)
        self.graph.bind("dartfx", DARTFX)

        for ttl_file in self.resource_dir.rglob("resources.ttl"):
            self.graph.parse(ttl_file, format="turtle")

    def save(self):
        """No longer used for a single file, as resources are saved individually."""
        pass

    def _save_resource(self, uri: URIRef, path: Path):
        """Serializes a specific resource's triples to its own mirrored directory."""
        resource_dir = self.resource_dir / path
        resource_dir.mkdir(parents=True, exist_ok=True)
        resource_file = resource_dir / "resources.ttl"

        # Create a temporary graph to serialize just THIS resource
        temp_graph = Graph()
        temp_graph.bind("dcterms", DCTERMS)
        temp_graph.bind("schema", SCHEMA)
        temp_graph.bind("dartfx", DARTFX)
        for t in self.graph.triples((uri, None, None)):
            temp_graph.add(t)
        temp_graph.serialize(destination=resource_file, format="turtle")

    def _cleanup_old_resource(self, old_path_str: str):
        """Removes the mirrored resource directory when a file is deleted or renamed."""
        import shutil

        old_dir = self.resource_dir / old_path_str
        if old_dir.exists() and old_dir.is_dir():
            shutil.rmtree(old_dir)

        # Prune empty parent directories up to self.resource_dir
        parent = old_dir.parent
        while parent != self.resource_dir and parent.is_dir():
            try:
                # Check if directory is empty
                if not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
                else:
                    break
            except OSError:
                break

    def get_resource_uri(self, uuid: UUID) -> URIRef:
        return URIRef(f"urn:uuid:{uuid}")

    def upsert_file_resource(
        self,
        uuid: UUID,
        path: Path,
        size_bytes: int,
        blake3_hash: str,
        file_type: str,
        created_at: datetime,
        updated_at: datetime,
    ):
        """Adds or updates a file resource within the RDF graph."""
        uri = self.get_resource_uri(uuid)

        # Check if the path changed for an existing resource (rename/move)
        old_path_str = None
        for p_literal in self.graph.objects(uri, DARTFX.path):
            old_path_str = str(p_literal)
            break

        # Clear existing properties for this URI to fully replace it
        self.graph.remove((uri, None, None))

        self.graph.add((uri, RDF.type, DARTFX.FileResource))
        self.graph.add((uri, RDF.type, SCHEMA.MediaObject))

        # Identifiers
        self.graph.add((uri, DARTFX.uuid, Literal(str(uuid))))
        self.graph.add((uri, DCTERMS.identifier, Literal(str(uuid))))

        # Path and Type
        self.graph.add((uri, DARTFX.path, Literal(path.as_posix())))
        self.graph.add((uri, DARTFX.filetype, Literal(file_type)))
        self.graph.add((uri, SCHEMA.fileFormat, Literal(file_type)))

        # Metrics
        self.graph.add((uri, DARTFX.sizeBytes, Literal(size_bytes, datatype=XSD.integer)))
        self.graph.add((uri, SCHEMA.contentSize, Literal(size_bytes, datatype=XSD.integer)))
        self.graph.add((uri, DARTFX.blake3, Literal(blake3_hash)))

        # Timestamps
        self.graph.add((uri, DCTERMS.created, Literal(created_at.isoformat(), datatype=XSD.dateTime)))
        self.graph.add((uri, SCHEMA.dateCreated, Literal(created_at.isoformat(), datatype=XSD.dateTime)))
        self.graph.add((uri, DCTERMS.modified, Literal(updated_at.isoformat(), datatype=XSD.dateTime)))
        self.graph.add((uri, SCHEMA.dateModified, Literal(updated_at.isoformat(), datatype=XSD.dateTime)))

        # Save this specific resource to its individual directory
        self._save_resource(uri, path)

        if old_path_str and old_path_str != path.as_posix():
            self._cleanup_old_resource(old_path_str)

    def remove_file_resource(self, uuid: UUID):
        """Removes a file resource, its triples, and its mirrored directory."""
        uri = self.get_resource_uri(uuid)
        old_path_str = None
        for p_literal in self.graph.objects(uri, DARTFX.path):
            old_path_str = str(p_literal)
            break

        self.graph.remove((uri, None, None))

        if old_path_str:
            self._cleanup_old_resource(old_path_str)

    def get_file_by_path(self, path_str: str) -> dict | None:
        """Looks up a file resource efficiently using its path."""
        q = """
        PREFIX dartfx: <https://dataartifex.org/workspace/>
        PREFIX dcterms: <http://purl.org/dc/terms/>
        SELECT ?uri ?uuid ?size ?hash ?type ?created ?modified
        WHERE {
            ?uri a dartfx:FileResource ;
                 dartfx:uuid ?uuid ;
                 dartfx:path ?path ;
                 dartfx:sizeBytes ?size ;
                 dartfx:blake3 ?hash ;
                 dartfx:filetype ?type ;
                 dcterms:created ?created ;
                 dcterms:modified ?modified .
        }
        """
        for row in self.graph.query(q, initBindings={"path": Literal(path_str)}):
            r: Any = row
            return {
                "uuid": str(r.uuid),
                "path": path_str,
                "size_bytes": int(r.size),
                "blake3_hash": str(r.hash),
                "type": str(r.type),
                "created_at": str(r.created),
                "updated_at": str(r.modified),
            }
        return None

    def get_all_files(self) -> list[dict]:
        """
        Extract files currently tracked in the KB.
        Returns a list of dicts with uuid, path, hash etc.
        """
        q = """
        PREFIX dartfx: <https://dataartifex.org/workspace/>
        PREFIX dcterms: <http://purl.org/dc/terms/>
        SELECT ?uri ?uuid ?path ?size ?hash ?type ?created ?modified
        WHERE {
            ?uri a dartfx:FileResource ;
                 dartfx:uuid ?uuid ;
                 dartfx:path ?path ;
                 dartfx:sizeBytes ?size ;
                 dartfx:blake3 ?hash ;
                 dartfx:filetype ?type ;
                 dcterms:created ?created ;
                 dcterms:modified ?modified .
        }
        """
        results = []
        for row in self.graph.query(q):
            r: Any = row
            results.append(
                {
                    "uuid": str(r.uuid),
                    "path": str(r.path),
                    "size_bytes": int(r.size),
                    "blake3_hash": str(r.hash),
                    "type": str(r.type),
                    "created_at": str(r.created),
                    "updated_at": str(r.modified),
                }
            )
        return results
