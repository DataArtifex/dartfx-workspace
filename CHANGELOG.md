# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0]

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
