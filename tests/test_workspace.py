"""
Unit tests for the Workspace management system.
"""

from dartfx.workspace.core import Workspace
from dartfx.workspace.models import FileType


def test_workspace_initialization(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)

    assert ws.is_initialized()
    assert (tmp_path / ".dartfx").exists()
    assert (tmp_path / "data").exists()
    assert (tmp_path / "code").exists()
    assert (tmp_path / "docs").exists()


def test_workspace_scanning(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)

    # Create mock files
    data_file = tmp_path / "data" / "dataset.csv"
    data_file.write_text("id,val\n1,10\n2,20")

    code_file = tmp_path / "code" / "script.py"
    code_file.write_text("print('hello')")

    # Scan
    ws.scan()

    files = ws.kb.get_all_files()
    assert len(files) == 2

    paths = {f["path"] for f in files}
    assert "data/dataset.csv" in paths
    assert "code/script.py" in paths

    # Stats
    stats = ws.stats()
    assert stats.total_files == 2
    assert stats.types_info[FileType.DATA].count == 1
    assert stats.types_info[FileType.CODE].count == 1


def test_workspace_rename_handling(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)
    file1 = tmp_path / "data" / "test.csv"
    file1.write_text("some content")

    ws.scan()
    files = ws.kb.get_all_files()
    orig_uuid = next(f["uuid"] for f in files if f["path"] == "data/test.csv")

    # Move file outside shell (simulated)
    file2 = tmp_path / "data" / "renamed.csv"
    file1.rename(file2)

    # Scan again
    ws.scan()
    new_files = ws.kb.get_all_files()
    assert len(new_files) == 1
    new_file = new_files[0]

    assert new_file["path"] == "data/renamed.csv"
    assert new_file["uuid"] == orig_uuid  # UUID should be preserved!


def test_find_nearest_initialized_path_prefers_closest_ancestor(tmp_path):
    root = tmp_path / "root"
    child = root / "child"
    grandchild = child / "grandchild"
    grandchild.mkdir(parents=True)

    Workspace.init(root)
    Workspace.init(child)

    found = Workspace.find_nearest_initialized_path(grandchild)
    assert found == child.resolve()


def test_find_parent_initialized_path_excludes_current_path(tmp_path):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)

    Workspace.init(parent)
    Workspace.init(child)

    found = Workspace.find_parent_initialized_path(child)
    assert found == parent.resolve()


def test_remove_path_cascades_fairify_artifacts(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)

    data_file = tmp_path / "data" / "sample.csv"
    data_file.write_text("a,b\n1,2\n")

    # Generate candidate artifacts
    artifacts = [
        tmp_path / "data" / "sample.csv.stats.csv",
        tmp_path / "data" / "sample.schema.json",
        tmp_path / "data" / "sample.freqs.csv",
        tmp_path / "data" / "sample.csv.idx",
        tmp_path / "data" / "sample.description.md",
        tmp_path / "data" / "sample.csv.stats.csv.data.jsonl",
        tmp_path / "data" / "sample.readstat.json",
    ]
    for art in artifacts:
        art.write_text("test artifact")

    # Unrelated files
    unrelated_file = tmp_path / "data" / "unrelated.csv"
    unrelated_file.write_text("x,y\n3,4\n")
    unrelated_art = tmp_path / "data" / "unrelated.stats.csv"
    unrelated_art.write_text("unrelated stats")

    ws.scan()
    assert len(ws.kb.get_all_files()) == 10

    removed = ws.remove_path("data/sample.csv", delete_artifacts=True)

    assert not data_file.exists()
    for art in artifacts:
        assert not art.exists()

    assert unrelated_file.exists()
    assert unrelated_art.exists()

    # Verify return list contains relative paths
    assert "data/sample.csv" in removed
    assert "data/sample.csv.stats.csv" in removed
    assert len(removed) == 8

    # Verify KB pruning
    remaining_kb_paths = {f["path"] for f in ws.kb.get_all_files()}
    assert "data/unrelated.csv" in remaining_kb_paths
    assert "data/unrelated.stats.csv" in remaining_kb_paths
    assert "data/sample.csv" not in remaining_kb_paths
    for art in artifacts:
        rel_art = art.relative_to(tmp_path).as_posix()
        assert rel_art not in remaining_kb_paths


def test_remove_path_without_delete_artifacts(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)

    data_file = tmp_path / "data" / "test.csv"
    data_file.write_text("col1\nval1\n")
    stats_file = tmp_path / "data" / "test.csv.stats.csv"
    stats_file.write_text("stats")

    ws.scan()
    assert len(ws.kb.get_all_files()) == 2

    removed = ws.remove_path("data/test.csv", delete_artifacts=False)
    assert not data_file.exists()
    assert stats_file.exists()
    assert removed == ["data/test.csv"]

    remaining_kb_paths = {f["path"] for f in ws.kb.get_all_files()}
    assert "data/test.csv" not in remaining_kb_paths
    assert "data/test.csv.stats.csv" in remaining_kb_paths


def test_remove_path_direct_artifact_deletion(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)

    data_file = tmp_path / "data" / "keep.csv"
    data_file.write_text("col1\nval1\n")
    stats_file = tmp_path / "data" / "keep.csv.stats.csv"
    stats_file.write_text("stats")

    ws.scan()
    assert len(ws.kb.get_all_files()) == 2

    # Deleting an artifact directly must NOT delete the source dataset
    removed = ws.remove_path("data/keep.csv.stats.csv", delete_artifacts=True)
    assert not stats_file.exists()
    assert data_file.exists()
    assert removed == ["data/keep.csv.stats.csv"]

    remaining_kb_paths = {f["path"] for f in ws.kb.get_all_files()}
    assert "data/keep.csv" in remaining_kb_paths
    assert "data/keep.csv.stats.csv" not in remaining_kb_paths


def test_kb_source_uuid_provenance(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)

    data_file = tmp_path / "data" / "source_dataset.csv"
    data_file.write_text("a,b\n1,2\n")
    stats_file = tmp_path / "data" / "source_dataset.csv.stats.csv"
    stats_file.write_text("stats")

    ws.scan()
    files = ws.kb.get_all_files()
    source_rec = next(f for f in files if f["path"] == "data/source_dataset.csv")
    s_uuid = source_rec["uuid"]

    # Register artifact with explicit source_uuid provenance
    ws.scanner.scan_path(stats_file, is_generated=True, generated_by="qsv", source_uuid=s_uuid)

    art_rec = ws.kb.get_file_by_path("data/source_dataset.csv.stats.csv")
    assert art_rec is not None
    assert art_rec.get("source_uuid") == s_uuid
    assert art_rec.get("is_generated") is True

    # Query artifacts by source UUID
    derived = ws.kb.get_artifacts_for_source(s_uuid)
    assert len(derived) == 1
    assert derived[0]["path"] == "data/source_dataset.csv.stats.csv"

    # Verify RDF serialization contains source provenance triples
    turtle = ws.export_rdf(art_rec["uuid"], rdf_format="turtle")
    assert "sourceUuid" in turtle
    assert s_uuid in turtle


def test_move_path_cascades_fairify_artifacts(tmp_path):
    ws = Workspace.init(tmp_path, create_dirs=True)

    data_file = tmp_path / "data" / "survey.csv"
    data_file.write_text("col1,col2\n10,20\n")

    artifacts = [
        tmp_path / "data" / "survey.csv.stats.csv",
        tmp_path / "data" / "survey.schema.json",
        tmp_path / "data" / "survey.freqs.csv",
        tmp_path / "data" / "survey.csv.idx",
        tmp_path / "data" / "survey.description.md",
    ]
    for art in artifacts:
        art.write_text("content")

    ws.scan()
    initial_files = {f["path"]: f["uuid"] for f in ws.kb.get_all_files()}
    source_uuid = initial_files["data/survey.csv"]
    stats_uuid = initial_files["data/survey.csv.stats.csv"]

    # Rename dataset via move_path
    new_dst = ws.move_path("data/survey.csv", "data/survey_2026.csv")
    assert new_dst == tmp_path / "data" / "survey_2026.csv"
    assert new_dst.exists()
    assert not data_file.exists()

    # Verify sidecars are renamed on disk
    expected_renamed = [
        tmp_path / "data" / "survey_2026.csv.stats.csv",
        tmp_path / "data" / "survey_2026.schema.json",
        tmp_path / "data" / "survey_2026.freqs.csv",
        tmp_path / "data" / "survey_2026.csv.idx",
        tmp_path / "data" / "survey_2026.description.md",
    ]
    for expected in expected_renamed:
        assert expected.exists(), f"Expected renamed artifact {expected.name} to exist"

    # Old artifacts must no longer exist
    for art in artifacts:
        assert not art.exists(), f"Old artifact {art.name} should have been renamed"

    # Verify Knowledge Base paths and UUID preservation
    new_files = {f["path"]: f["uuid"] for f in ws.kb.get_all_files()}
    assert "data/survey_2026.csv" in new_files
    assert new_files["data/survey_2026.csv"] == source_uuid
    assert "data/survey_2026.csv.stats.csv" in new_files
    assert new_files["data/survey_2026.csv.stats.csv"] == stats_uuid

    for art in artifacts:
        rel = art.relative_to(tmp_path).as_posix()
        assert rel not in new_files

    # Verify fairify status remains up-to-date
    from dartfx.workspace.utils import is_fairify_up_to_date

    assert is_fairify_up_to_date(new_dst) is True
