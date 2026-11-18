"""Tests for workspace governance policies: rename rules, content zoning, and settings persistence."""

import pytest

from dartfx.workspace.core import Workspace
from dartfx.workspace.policy import (
    IngestionPolicyViolationError,
    RenameMode,
    RenamePolicyViolationError,
)


def test_default_settings_and_persistence(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)
    settings = ws.get_settings()

    assert settings.rename.mode == RenameMode.SAME_FORMAT
    assert settings.rename.allow_sidecar_rename is False
    assert settings.ingestion.enforce_zones is True
    assert [z.pattern for z in settings.ingestion.zones] == [
        "data/**",
        "docs/**",
        "code/**",
        "meta/**",
        "work/**",
    ]

    # Update and verify persistence in .dartfx/settings.json
    updated = ws.update_settings({"rename": {"mode": "strict"}})
    assert updated.rename.mode == RenameMode.STRICT
    assert ws.settings_path.exists()

    reloaded = Workspace(tmp_path).get_settings()
    assert reloaded.rename.mode == RenameMode.STRICT


def test_rename_policy_same_format_default(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)
    ws.ingest_file(b"id,val\n1,10\n", "data/survey.csv")
    ws.ingest_file(b"key: value\n", "meta/config.yaml")
    ws.ingest_file(b"col1,col2\na,1\nb,2\n", "data/raw_export.dat")
    ws.ingest_file(b"col,mean\nval,10\n", "data/survey.csv.stats.csv")

    # 1. Same extension succeeds
    moved_csv = ws.move_path("data/survey.csv", "data/survey_v2.csv")
    assert moved_csv.name == "survey_v2.csv"
    # Sidecar cascaded along with parent
    assert (tmp_path / "data" / "survey_v2.csv.stats.csv").exists()

    # 2. Equivalent format (.yaml -> .yml) succeeds under same_format
    moved_yml = ws.move_path("meta/config.yaml", "meta/config.yml")
    assert moved_yml.name == "config.yml"

    # 3. Misnamed .dat with CSV content -> .csv succeeds under same_format
    moved_dat = ws.move_path("data/raw_export.dat", "data/raw_export.csv")
    assert moved_dat.name == "raw_export.csv"

    # 4. Cross-format rename (.csv -> .parquet or .txt) is rejected
    with pytest.raises(RenamePolicyViolationError, match="same_format"):
        ws.move_path("data/survey_v2.csv", "data/survey_v2.parquet")

    with pytest.raises(RenamePolicyViolationError, match="same_format"):
        ws.move_path("data/survey_v2.csv", "data/survey_v2.txt")

    # 5. Direct sidecar rename is rejected
    with pytest.raises(RenamePolicyViolationError, match="system-generated artifact"):
        ws.move_path("data/survey_v2.csv.stats.csv", "data/other.stats.csv")

    # 6. Explicit policy override bypasses restriction
    overridden = ws.move_path("data/survey_v2.csv", "data/survey_v2.tsv", allow_policy_override=True)
    assert overridden.name == "survey_v2.tsv"


def test_rename_policy_strict_and_permissive(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)
    ws.ingest_file(b"key: value\n", "meta/items.yaml")
    ws.ingest_file(b"a,b\n1,2\n", "data/items.csv")

    # Strict: even equivalent .yaml -> .yml is rejected
    ws.update_settings({"rename": {"mode": "strict"}})
    with pytest.raises(RenamePolicyViolationError, match="strict"):
        ws.move_path("meta/items.yaml", "meta/items.yml")

    assert ws.move_path("meta/items.yaml", "meta/items_v2.yaml").name == "items_v2.yaml"

    # Permissive: cross-format rename is allowed
    ws.update_settings({"rename": {"mode": "permissive"}})
    assert ws.move_path("data/items.csv", "data/items.txt").name == "items.txt"


def test_ingestion_zone_policies(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)

    # Valid placements
    ws.ingest_file(b"a,b\n1,2\n", "data/metrics.csv")
    ws.ingest_file(b"%PDF-1.4\n...", "docs/codebook.pdf")
    ws.ingest_file(b"# Study Notes\n", "docs/readme.md")
    ws.ingest_file(b"print('hello')\n", "code/clean.py")
    ws.ingest_file(b'{"@context": {}}\n', "meta/schema.jsonld")
    ws.ingest_file(b"scratch content", "work/temp.txt")
    ws.ingest_file(b"root notes", "notes.txt")

    # Companion system-generated metadata/doc sidecars are permitted in data/
    ws.ingest_file(b'{"fields": []}', "data/metrics.schema.json")
    ws.ingest_file(b"# Description", "data/metrics.description.md")

    # Invalid placements into data/
    with pytest.raises(IngestionPolicyViolationError, match="data/\\*\\*"):
        ws.ingest_file(b"%PDF-1.4\n...", "data/report.pdf")

    with pytest.raises(IngestionPolicyViolationError, match="data/\\*\\*"):
        ws.ingest_file(b"print('hi')\n", "data/script.py")

    # Invalid placements into docs/, code/, meta/
    with pytest.raises(IngestionPolicyViolationError, match="docs/\\*\\*"):
        ws.ingest_file(b"a,b\n1,2\n", "docs/data.csv")

    with pytest.raises(IngestionPolicyViolationError, match="code/\\*\\*"):
        ws.ingest_file(b"a,b\n1,2\n", "code/data.csv")

    with pytest.raises(IngestionPolicyViolationError, match="meta/\\*\\*"):
        ws.ingest_file(b"print('hi')\n", "meta/script.py")

    # Cross-zone move into incompatible zone is blocked
    with pytest.raises(IngestionPolicyViolationError, match="data/\\*\\*"):
        ws.move_path("docs/codebook.pdf", "data/codebook.pdf")

    # Disabling enforce_zones allows any placement
    ws.update_settings({"ingestion": {"enforce_zones": False}})
    entry = ws.ingest_file(b"%PDF-1.4\n...", "data/report.pdf")
    assert entry.path == "data/report.pdf"
