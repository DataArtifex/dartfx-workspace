# Implementation Guide: Dartfx Workspace

This document describes the technical architecture and implementation details of the `dartfx-workspace` package.

## 🏗 Knowledge Base Architecture

The Knowledge Base (KB) implements a **Decentralized Mirrored Storage** pattern. Instead of a single monolithic database, resource metadata is stored alongside the workspace structure in a mirrored hierarchy.

### Mirrored Storage
- **Location**: `.dartfx/kb/workspace/`
- **Structure**: Mirrors the workspace's relative file paths.
- **Resource File**: Each resource (file) has a dedicated directory containing a `resources.ttl` file.
  - Example: `data/raw/survey.csv` -> `.dartfx/kb/workspace/data/raw/survey.csv/resources.ttl`

### RDF Graph
- The system uses `rdflib` to maintain an in-memory Graph for fast querying.
- The graph is hydrated by crawling the mirrored storage directories on startup.
- Vocabularies:
  - `dcterms`: IDs, paths, hashes, and timestamps.
  - `schema`: Mapped to `MediaObject` for external interoperability.
  - `dartfx`: Internal workspace-specific properties.

## 🕵️‍♂️ Sniffing & Classification

We employ a multi-phase, content-first sniffing pipeline designed for scientific and technical data.

### Phase A: Classification
1. **Extension Sniffer**: Fast, zero-I/O check against a known map (e.g., .sql, .sas7bdat).
   - *Note*: Directory names (heuristics) are strictly ignored in favor of technical signatures.
2. **Magic Byte Sniffer**: Binary signature detection (reads first 64 bytes).
3. **Text Heuristic Sniffer**: Analyzes character distributions and delimiters (reads first 10KB).

### Phase B: Attribute Enrichment
Extracted attributes (e.g., column count, row count, delimiter) are added to the resource triple during indexing.

## 🔄 Synchronization Engine (Scanner)

The `Scanner` provides robust synchronization between the physical filesystem and the semantic Knowledge Base.

### Targeted Scanning
The `scan` operation is context-aware:
- **Scope**: Can target the workspace root or any subdirectory.
- **Cleanup**: Implements **Scoped Cleanup**. Only records for files missing within the target scan area are removed from the KB, preventing metadata loss for resources in other parts of the workspace.

### Atomic Moves & Deletes
- **`handle_move`**: Efficiently updates KB paths and shifts mirrored metadata directories. Relies on stable UUID tracking rather than path-based identity.
- **`handle_remove`**: Recursively prunes KB records and mirrored storage for deleted files/directories.

## 🐚 Shell Environment

The interactive shell is built on `prompt_toolkit` and optimized for a **mouse-native, minimalist experience**.
- **Minimalism**: Interactive elements (like metadata links) are hidden behind small, non-obvious icons (📂) to avoid clutter.
- **Zero-Typing**: Contextual auto-completion and context-awareness (like `scan` defaulting to `.`) minimize keyboard input requirements.

## 🧩 Programmatic API, Spaces, Access Policy & Async Tasks

All core workspace features are exposed programmatically on `Workspace`, `Space`, `AccessPolicy`, and `dartfx.workspace.tasks` so Python scripts, notebooks, the CLI shell, and `dartfx-workspace-api` share a single engine:

- **Path Sandboxing & File Lifecycle (`core.py`)**: `Workspace.resolve_safe_path()` prevents directory traversal and restricts `.dartfx` internal edits. `list_files()`, `get_tree()`, `preview_file()`, `ingest_file()`, `resolve_download_path()`, `create_archive()`, `mkdir()`, `move_path()`, `copy_path()`, and `remove_path()` return structured Pydantic models and synchronize KB records automatically.
- **Knowledge Base & Queries (`kb.py`, `core.py`)**: `get_file_by_uuid()`, `export_resource_rdf()`, `export_workspace_rdf()`, `query_sparql()`, and `query_tabular()` (using DuckDB when installed, Polars `SQLContext`, or SQLite fallback for read-only `SELECT`/`WITH` SQL queries).
- **Spaces & Ephemeral Sandboxes (`spaces.py`)**: `Space` aggregates workspaces, enforces cumulative storage quotas (`SpaceStats`), and provisions/resets default public sandbox workspaces (`provision_ephemeral_workspace()`, `reset_ephemeral_workspace()`).
- **3-Tier Access Policy (`access.py`)**: `AccessPolicy` authorizes `Principal` objects across `AccessTier` (`anonymous`, `user`, `admin`) and `Visibility` (`public`, `team`, `private`), raising `WorkspaceAccessDeniedError` or `QuotaExceededError`.
- **Async Task & Event Protocol (`tasks.py`)**: `run_scan_task()`, `run_fairify_task()`, `run_readstat_task()`, `run_tocsv_task()`, and `stream_task()` emit typed `TaskEvent` Pydantic models via callback hooks or Python `async` generators.
- **File Provenance & Command Applicability (`utils.py`, `models.py`)**: Differentiates user-provided files (`is_generated=False`) from system-generated profiling outputs (`is_generated=True`, `generated_by="qsv"|"readstat"`). Computes `applicable_actions` dynamically (`fairify` is strictly restricted to user-provided CSV and Parquet files, while `tocsv` and `readstat` require statistical files with extensions `dta|por|sas7bdat|sav|xpt|zsav`). Both programmatic APIs and the CLI shell enforce these guardrails.
