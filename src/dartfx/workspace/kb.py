"""
RDF Knowledge Base interactions using rdflib.
"""

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, XSD

from dartfx.workspace.models import SparqlResult
from dartfx.workspace.utils import detect_system_generated

DARTFX = Namespace("https://dataartifex.org/workspace/")
SCHEMA = Namespace("https://schema.org/")

_RDF_FORMAT_ALIASES: dict[str, str] = {
    "ttl": "turtle",
    "turtle": "turtle",
    "jsonld": "json-ld",
    "json-ld": "json-ld",
    "rdfxml": "xml",
    "xml": "xml",
    "n3": "n3",
    "nt": "nt",
}


def _normalize_rdf_format(rdf_format: str) -> str:
    fmt = _RDF_FORMAT_ALIASES.get(rdf_format.strip().lower())
    if not fmt:
        allowed = ", ".join(sorted(_RDF_FORMAT_ALIASES.keys()))
        raise ValueError(f"Unsupported RDF format '{rdf_format}'. Expected one of: {allowed}")
    return fmt


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

    def get_resource_metadata_path(self, path: Path) -> Path:
        """Returns the directory where a specific resource's metadata is stored."""
        return self.resource_dir / path

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
        *,
        file_format: str = "undetermined",
        mime_type: str | None = None,
        attributes: dict[str, str] | None = None,
        is_generated: bool = False,
        generated_by: str | None = None,
        source_uuid: UUID | str | None = None,
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
        self.graph.add((uri, DARTFX.fileType, Literal(file_type)))
        self.graph.add((uri, SCHEMA.fileFormat, Literal(file_type)))

        # Format classification
        self.graph.add((uri, DARTFX.fileFormat, Literal(file_format)))
        if mime_type:
            self.graph.add((uri, DARTFX.mimeType, Literal(mime_type)))

        # Provenance / system generation
        self.graph.add((uri, DARTFX.isGenerated, Literal(is_generated, datatype=XSD.boolean)))
        if generated_by:
            self.graph.add((uri, DARTFX.generatedBy, Literal(generated_by)))
        if source_uuid:
            self.graph.add((uri, DARTFX.sourceUuid, Literal(str(source_uuid))))
            self.graph.add((uri, DCTERMS.source, URIRef(f"urn:uuid:{source_uuid}")))

        # Metrics
        self.graph.add((uri, DARTFX.sizeBytes, Literal(size_bytes, datatype=XSD.integer)))
        self.graph.add((uri, SCHEMA.contentSize, Literal(size_bytes, datatype=XSD.integer)))
        self.graph.add((uri, DARTFX.blake3, Literal(blake3_hash)))

        # Timestamps
        self.graph.add((uri, DCTERMS.created, Literal(created_at.isoformat(), datatype=XSD.dateTime)))
        self.graph.add((uri, SCHEMA.dateCreated, Literal(created_at.isoformat(), datatype=XSD.dateTime)))
        self.graph.add((uri, DCTERMS.modified, Literal(updated_at.isoformat(), datatype=XSD.dateTime)))
        self.graph.add((uri, SCHEMA.dateModified, Literal(updated_at.isoformat(), datatype=XSD.dateTime)))

        # Format-specific attributes (e.g. textDelimiter, fileFormatVersion)
        if attributes:
            for key, value in attributes.items():
                self.graph.add((uri, DARTFX[key], Literal(value)))

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

    _FILE_SELECT_QUERY = """
        PREFIX dartfx: <https://dataartifex.org/workspace/>
        PREFIX dcterms: <http://purl.org/dc/terms/>
        SELECT ?uri ?uuid ?path ?size ?hash ?type ?format ?mime ?created ?modified
               ?is_generated ?generated_by ?source_uuid
        WHERE {
            ?uri a dartfx:FileResource ;
                 dartfx:uuid ?uuid ;
                 dartfx:path ?path ;
                 dartfx:sizeBytes ?size ;
                 dartfx:blake3 ?hash ;
                 dartfx:fileType ?type ;
                 dartfx:fileFormat ?format ;
                 dcterms:created ?created ;
                 dcterms:modified ?modified .
            OPTIONAL { ?uri dartfx:mimeType ?mime . }
            OPTIONAL { ?uri dartfx:isGenerated ?is_generated . }
            OPTIONAL { ?uri dartfx:generatedBy ?generated_by . }
            OPTIONAL { ?uri dartfx:sourceUuid ?source_uuid . }
        }
        """

    @staticmethod
    def _row_to_file_dict(row: Any, override_path: str | None = None) -> dict[str, Any]:
        target_path = override_path if override_path is not None else str(row.path)
        is_gen_val = getattr(row, "is_generated", None)
        if is_gen_val is not None:
            is_generated = str(is_gen_val).lower() in ("true", "1")
        else:
            is_generated, _ = detect_system_generated(target_path)

        gen_by_val = getattr(row, "generated_by", None)
        if gen_by_val is not None and str(gen_by_val).strip():
            generated_by = str(gen_by_val).strip()
        else:
            _, generated_by = detect_system_generated(target_path)

        source_uuid_val = getattr(row, "source_uuid", None)
        source_uuid = (
            str(source_uuid_val).strip() if source_uuid_val is not None and str(source_uuid_val).strip() else None
        )

        return {
            "uuid": str(row.uuid),
            "path": target_path,
            "size_bytes": int(row.size),
            "blake3_hash": str(row.hash),
            "type": str(row.type),
            "file_format": str(row.format),
            "mime_type": str(row.mime) if hasattr(row, "mime") and row.mime else None,
            "created_at": str(row.created),
            "updated_at": str(row.modified),
            "is_generated": is_generated,
            "generated_by": generated_by,
            "source_uuid": source_uuid,
        }

    def get_artifacts_for_source(self, source_uuid: UUID | str) -> list[dict[str, Any]]:
        """Return all registered artifact records derived from the given source file UUID."""
        target = str(source_uuid)
        return [f for f in self.get_all_files() if f.get("source_uuid") == target]

    def get_file_by_path(self, path_str: str) -> dict[str, Any] | None:
        """Looks up a file resource efficiently using its path."""
        for row in self.graph.query(self._FILE_SELECT_QUERY, initBindings={"path": Literal(path_str)}):
            return self._row_to_file_dict(row, override_path=path_str)
        return None

    def get_file_by_uuid(self, uuid_val: UUID | str) -> dict[str, Any] | None:
        """Looks up a file resource efficiently using its UUID."""
        uuid_str = str(uuid_val)
        for row in self.graph.query(self._FILE_SELECT_QUERY, initBindings={"uuid": Literal(uuid_str)}):
            return self._row_to_file_dict(row)
        return None

    def get_resource_attributes(self, uuid: UUID) -> dict[str, str]:
        """Returns all dynamic attributes for a resource in the DARTFX namespace."""
        uri = self.get_resource_uri(uuid)
        attrs = {}
        for p, o in self.graph.predicate_objects(uri):
            p_str = str(p)
            if p_str.startswith(str(DARTFX)):
                key = p_str.replace(str(DARTFX), "")
                # Skip core fields we handle separately
                if key not in [
                    "uuid",
                    "path",
                    "fileType",
                    "fileFormat",
                    "sizeBytes",
                    "blake3",
                    "mimeType",
                    "isGenerated",
                    "generatedBy",
                ]:
                    attrs[key] = str(o)
        return attrs

    def get_all_files(self) -> list[dict[str, Any]]:
        """
        Extract files currently tracked in the KB.
        Returns a list of dicts with uuid, path, hash etc.
        """
        return [self._row_to_file_dict(row) for row in self.graph.query(self._FILE_SELECT_QUERY)]

    def export_resource_rdf(self, uuid_val: UUID | str, rdf_format: str = "turtle") -> str:
        """Serialize RDF triples for a specific file resource in the requested format."""
        fmt = _normalize_rdf_format(rdf_format)
        parsed_uuid = uuid_val if isinstance(uuid_val, UUID) else UUID(str(uuid_val))
        uri = self.get_resource_uri(parsed_uuid)

        triples = list(self.graph.triples((uri, None, None)))
        if not triples:
            raise KeyError(f"Resource not found in Knowledge Base: {parsed_uuid}")

        temp_graph = Graph()
        temp_graph.bind("dcterms", DCTERMS)
        temp_graph.bind("schema", SCHEMA)
        temp_graph.bind("dartfx", DARTFX)
        for triple in triples:
            temp_graph.add(triple)
        return temp_graph.serialize(format=fmt)

    def export_workspace_rdf(self, rdf_format: str = "turtle") -> str:
        """Serialize the full workspace RDF Knowledge Base graph."""
        fmt = _normalize_rdf_format(rdf_format)
        return self.graph.serialize(format=fmt)

    def query_sparql(self, query_str: str) -> SparqlResult:
        """Execute a read-only SPARQL query (SELECT, ASK, CONSTRUCT, DESCRIBE) against the KB."""
        cleaned = query_str.strip()
        if not cleaned:
            raise ValueError("SPARQL query must not be empty.")

        res: Any = self.graph.query(cleaned)
        res_type = getattr(res, "type", None)

        if res_type == "ASK":
            val = "true" if bool(res.askAnswer) else "false"
            return SparqlResult(columns=["result"], rows=[{"result": val}], row_count=1)

        if res_type in ("CONSTRUCT", "DESCRIBE") or (hasattr(res, "graph") and res.graph is not None):
            triples_rows: list[dict[str, str | None]] = []
            for s, p, o in res.graph:
                triples_rows.append({"subject": str(s), "predicate": str(p), "object": str(o)})
            return SparqlResult(
                columns=["subject", "predicate", "object"],
                rows=triples_rows,
                row_count=len(triples_rows),
            )

        columns = [str(v) for v in (res.vars or [])]
        rows: list[dict[str, str | None]] = []
        for row in res:
            row_dict: dict[str, str | None] = {}
            for idx, col in enumerate(columns):
                cell = row[idx]
                row_dict[col] = str(cell) if cell is not None else None
            rows.append(row_dict)
        return SparqlResult(columns=columns, rows=rows, row_count=len(rows))

    def wipe(self):
        """Wipes the entire knowledge base by deleting all resource files and clearing the graph."""
        import shutil

        if self.resource_dir.exists():
            shutil.rmtree(self.resource_dir)
        self.resource_dir.mkdir(parents=True, exist_ok=True)
        self.graph = Graph()
        self.graph.bind("dcterms", DCTERMS)
        self.graph.bind("schema", SCHEMA)
        self.graph.bind("dartfx", DARTFX)
