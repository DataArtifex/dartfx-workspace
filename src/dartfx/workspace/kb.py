"""
RDF Knowledge Base interactions using rdflib.
"""
from pathlib import Path
from uuid import UUID
from datetime import datetime

from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import DCTERMS, RDF, XSD

DARTFX = Namespace("http://dartfx.org/workspace/")
SCHEMA = Namespace("https://schema.org/")

class KnowledgeBase:
    """
    Manages workspace knowledge base and state persistence using an RDF Graph.
    """
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.kb_dir = self.workspace_path / ".dartfx" / "kb" / "turtle"
        self.resource_dir = self.kb_dir / "files"
        self.graph = Graph()
        self.resource_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        """Loads all individual turtle files from the resource directory."""
        self.graph.bind("dcterms", DCTERMS)
        self.graph.bind("schema", SCHEMA)
        self.graph.bind("dartfx", DARTFX)
        
        for ttl_file in self.resource_dir.glob("*.ttl"):
            self.graph.parse(ttl_file, format="turtle")

    def save(self):
        """No longer used for a single file, as resources are saved individually."""
        pass

    def _save_resource(self, uuid: UUID, uri: URIRef):
        """Serializes a specific resource's triples to its own file."""
        resource_file = self.resource_dir / f"{uuid}.ttl"
        # Create a temporary graph to serialize just THIS resource
        temp_graph = Graph()
        temp_graph.bind("dcterms", DCTERMS)
        temp_graph.bind("schema", SCHEMA)
        temp_graph.bind("dartfx", DARTFX)
        for t in self.graph.triples((uri, None, None)):
            temp_graph.add(t)
        temp_graph.serialize(destination=resource_file, format="turtle")

    def get_resource_uri(self, uuid: UUID) -> URIRef:
        return URIRef(f"urn:uuid:{uuid}")

    def upsert_file_resource(self, uuid: UUID, path: Path, size_bytes: int, blake3_hash: str,
                             file_type: str, created_at: datetime, updated_at: datetime):
        """Adds or updates a file resource within the RDF graph."""
        uri = self.get_resource_uri(uuid)
        
        # Clear existing properties for this URI to fully replace it
        self.graph.remove((uri, None, None))
        
        self.graph.add((uri, RDF.type, DARTFX.FileResource))
        self.graph.add((uri, RDF.type, SCHEMA.MediaObject))
        
        # Identifiers
        self.graph.add((uri, DCTERMS.identifier, Literal(str(uuid))))
        self.graph.add((uri, SCHEMA.identifier, Literal(str(uuid))))
        
        # Path and Type
        self.graph.add((uri, DARTFX.path, Literal(str(path))))
        self.graph.add((uri, DARTFX.filetype, Literal(file_type)))
        self.graph.add((uri, SCHEMA.fileFormat, Literal(file_type)))
        
        # Metrics
        self.graph.add((uri, DARTFX.sizeBytes, Literal(size_bytes, datatype=XSD.integer)))
        self.graph.add((uri, SCHEMA.contentSize, Literal(size_bytes, datatype=XSD.integer)))
        self.graph.add((uri, DARTFX.blake3Hash, Literal(blake3_hash)))
        
        # Timestamps
        self.graph.add((uri, DCTERMS.created, Literal(created_at.isoformat(), datatype=XSD.dateTime)))
        self.graph.add((uri, SCHEMA.dateCreated, Literal(created_at.isoformat(), datatype=XSD.dateTime)))
        self.graph.add((uri, DCTERMS.modified, Literal(updated_at.isoformat(), datatype=XSD.dateTime)))
        self.graph.add((uri, SCHEMA.dateModified, Literal(updated_at.isoformat(), datatype=XSD.dateTime)))
        
        # Save this specific resource to its individual file
        self._save_resource(uuid, uri)

    def remove_file_resource(self, uuid: UUID):
        """Removes a file resource, its triples, and its turtle file."""
        uri = self.get_resource_uri(uuid)
        self.graph.remove((uri, None, None))
        resource_file = self.resource_dir / f"{uuid}.ttl"
        if resource_file.exists():
            resource_file.unlink()

    def get_all_files(self) -> list[dict]:
        """
        Extract files currently tracked in the KB.
        Returns a list of dicts with uuid, path, hash etc.
        """
        q = """
        SELECT ?uri ?id ?path ?size ?hash ?type ?created ?modified
        WHERE {
            ?uri a <http://dartfx.org/workspace/FileResource> ;
                 <http://purl.org/dc/terms/identifier> ?id ;
                 <http://dartfx.org/workspace/path> ?path ;
                 <http://dartfx.org/workspace/sizeBytes> ?size ;
                 <http://dartfx.org/workspace/blake3Hash> ?hash ;
                 <http://dartfx.org/workspace/filetype> ?type ;
                 <http://purl.org/dc/terms/created> ?created ;
                 <http://purl.org/dc/terms/modified> ?modified .
        }
        """
        results = []
        for row in self.graph.query(q):
            results.append({
                "uuid": str(row.id),
                "path": str(row.path),
                "size_bytes": int(row.size),
                "blake3_hash": str(row.hash),
                "type": str(row.type),
                "created_at": str(row.created),
                "updated_at": str(row.modified),
            })
        return results
