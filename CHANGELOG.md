# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0]

- Added extensible workspace governance policies (`dartfx.workspace.policy`): `WorkspaceSettings` persisted in `.dartfx/settings.json` with system-level environment overrides (`DARTFX_RENAME_MODE`, `DARTFX_ENFORCE_ZONES`).
- Added `RenamePolicy` defaulting to `RenameMode.SAME_FORMAT` (allowing compatible format renames like `.yaml` $\leftrightarrow$ `.yml` or `.dat` $\rightarrow$ `.csv` when sniffed as CSV, while blocking cross-format renames and direct sidecar renames) along with `strict`, `same_type`, and `permissive` modes.
- Added path-based `IngestionPolicy` and `ZoneRule` content zoning for `data/**`, `docs/**`, `code/**`, `meta/**`, and `work/**`, enforced during `ingest_file`, `copy_path`, and cross-zone `move_path` with companion sidecar exemptions.
- Added explicit UID-based derivation relationships in the Knowledge Base using `dartfx:sourceUuid` and `dcterms:source`, linking generated FAIRify and ReadStat metadata artifacts directly to the source dataset's UUID.
- Added `KnowledgeBase.get_artifacts_for_source(...)` and enriched `FileResource`, `FileEntry`, `TreeNode`, and `ResourceDetail` models with `source_uuid`.
- Added cascading artifact renames in `Workspace.move_path(...)` and shell `mv` (`handle_mv`) via `compute_renamed_artifact_path` and `Scanner.handle_moves`: moving or renaming a user dataset cascades the rename to all its existing FAIRification sidecars on disk and in the Knowledge Base while preserving each artifact's stable UUID and maintaining `up_to_date` status.
- Added cascading removal of related FAIRification and system-generated artifacts (e.g. `.stats.csv`, `.stats.csv.data.jsonl`, `.stats.csv.json`, `.schema.json`, `.freqs.csv`, `.freqs.long.csv`, `.idx`, `.description.md`, `.readstat.json`) in `Workspace.remove_path(...)` when deleting a primary dataset, with safety guardrails ensuring direct artifact deletion does not cascade.
- Updated `Scanner.handle_remove` to accept batches of target paths (`Path | Sequence[Path]`) and prune all associated records from the Knowledge Base in a single save.
- Enhanced shell `rm` command to utilize `Workspace.remove_path` and display feedback when related artifacts are cleaned up alongside the primary file.

- Added provenance tracking to differentiate user-provided files from system-generated artifacts (e.g. QSV frequency tables, profiling stats, indexes, schemas, and ReadStat metadata JSON).
- Added `compute_applicable_actions`, `is_fairifiable_file`, `is_statistical_file`, and `detect_system_generated` helpers to govern command eligibility per file.
- Added `is_fairify_up_to_date` and `get_fairify_status` detection based on artifact freshness (`mtime >= source mtime`); omits redundant `fairify` from `applicable_actions` when up-to-date while allowing force rerun via `--force` or `force=True`.
- Enforced FAIRification guardrails: only user-provided CSV and Parquet files can be FAIRified (rejects system-generated profiling artifacts and already up-to-date files unless forced).
- Enforced `to_csv` and `readstat` guardrails: restricted to supported statistical data formats (`dta`, `por`, `sas7bdat`, `sav`, `xpt`, `zsav`).
- Enriched `FileResource`, `FileEntry`, `TreeNode`, and `ResourceDetail` models with `is_generated`, `generated_by`, and `applicable_actions`.
- Added programmatic `Workspace` APIs (`list_files`, `get_tree`, `preview_file`, `get_resource_detail`, `update_resource_metadata`, `export_rdf`, `ingest_file`, `resolve_download_path`, `create_archive`, `mkdir`, `move_path`, `copy_path`, `remove_path`, `query_sparql`, `query_tabular`).
- Added `KnowledgeBase` UUID lookup (`get_file_by_uuid`), RDF export (`export_resource_rdf`, `export_workspace_rdf`), and SPARQL execution (`query_sparql`).
- Added `Space` and ephemeral public sandbox provisioning/reset (`dartfx.workspace.spaces`).
- Added 3-tier `AccessPolicy`, `Principal`, `AccessTier`, `Visibility`, and storage quota checks (`dartfx.workspace.access`).
- Added programmatic task runners (`run_scan_task`, `run_fairify_task`, `run_readstat_task`, `run_tocsv_task`) and async event generator `stream_task` emitting `TaskEvent` models (`dartfx.workspace.tasks`).
