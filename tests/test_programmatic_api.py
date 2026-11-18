"""
Comprehensive tests for the programmatic workspace, access, spaces, file ingest/export,
SPARQL/tabular querying, and async TaskEvent streaming APIs in dartfx-workspace.
"""

import asyncio
import json
import zipfile
from unittest.mock import patch

import pytest

from dartfx.workspace import (
    AccessPolicy,
    AccessTier,
    Action,
    Principal,
    QuotaExceededError,
    Space,
    SpaceConfig,
    TaskEvent,
    TaskStatus,
    TaskType,
    Visibility,
    WorkspaceAccessDeniedError,
    WorkspaceConfig,
    WorkspacePathTraversalError,
    run_fairify_task,
    run_readstat_task,
    run_scan_task,
    run_tocsv_task,
    stream_task,
)


class _Proc:
    def __init__(self):
        self.returncode = 0
        self.stdout = "ok"
        self.stderr = ""


def test_access_policy_three_tiers(tmp_path):
    anon = Principal()
    user = Principal(id="alice", tier=AccessTier.USER, label="Alice", team_ids=["team-a"], allowed_space_ids=["sp-1"])
    admin = Principal(id="root", tier=AccessTier.ADMIN, label="Admin")

    pub_ws = WorkspaceConfig(
        id="ws-pub", slug="pub", name="Public", path=tmp_path / "pub", visibility=Visibility.PUBLIC
    )
    priv_ws = WorkspaceConfig(
        id="ws-priv",
        slug="priv",
        name="Private",
        path=tmp_path / "priv",
        visibility=Visibility.PRIVATE,
        owner_id="alice",
    )
    other_priv_ws = WorkspaceConfig(
        id="ws-bob",
        slug="bob",
        name="Bob Private",
        path=tmp_path / "bob",
        visibility=Visibility.PRIVATE,
        owner_id="bob",
    )
    team_ws = WorkspaceConfig(
        id="ws-team",
        slug="team",
        name="Team A",
        path=tmp_path / "team",
        space_id="sp-1",
        visibility=Visibility.TEAM,
        team_id="team-a",
    )

    assert AccessPolicy.can_access_workspace(anon, pub_ws, Action.READ)
    assert AccessPolicy.can_access_workspace(anon, pub_ws, Action.WRITE)
    assert not AccessPolicy.can_access_workspace(anon, pub_ws, Action.ADMIN)
    assert not AccessPolicy.can_access_workspace(anon, priv_ws, Action.READ)
    assert not AccessPolicy.can_access_workspace(anon, team_ws, Action.READ)

    assert AccessPolicy.can_access_workspace(user, priv_ws, Action.WRITE)
    assert not AccessPolicy.can_access_workspace(user, other_priv_ws, Action.READ)
    assert AccessPolicy.can_access_workspace(user, team_ws, Action.EXECUTE)
    assert not AccessPolicy.can_access_workspace(user, team_ws, Action.ADMIN)

    assert AccessPolicy.can_access_workspace(admin, other_priv_ws, Action.ADMIN)
    with pytest.raises(WorkspaceAccessDeniedError):
        AccessPolicy.authorize(anon, team_ws, Action.READ)


def test_space_ephemeral_provision_stats_and_quota(tmp_path):
    space_root = tmp_path / "public-space"
    ws_dir = space_root / "sandbox"
    ws = Space.provision_ephemeral_workspace(ws_dir)

    assert ws.is_initialized()
    assert (ws_dir / "data" / "sample_survey.csv").exists()
    assert (ws_dir / "docs" / "README.md").exists()
    assert (ws_dir / "meta" / "catalog.json").exists()

    space_cfg = SpaceConfig(
        id="sp-pub",
        slug="public",
        name="Public Space",
        root_path=space_root,
        storage_quota_bytes=1024 * 1024,
        visibility=Visibility.PUBLIC,
    )
    space = Space(space_cfg)
    stats = space.stats([ws])
    assert stats.workspace_count == 1
    assert stats.total_files == 3
    assert stats.total_size_bytes > 0
    assert stats.quota_used_pct is not None

    with pytest.raises(QuotaExceededError):
        space.check_space_quota(additional_bytes=2 * 1024 * 1024)

    # Modify and reset ephemeral workspace
    (ws_dir / "data" / "temp_extra.txt").write_text("temporary", encoding="utf-8")
    reset_ws = Space.reset_ephemeral_workspace(ws_dir)
    assert not (ws_dir / "data" / "temp_extra.txt").exists()
    assert reset_ws.stats().total_files == 3


def test_ingest_download_archive_and_path_sandboxing(tmp_path):
    ws = Space.provision_ephemeral_workspace(tmp_path / "ws")

    # Traversal and .dartfx protection
    with pytest.raises(WorkspacePathTraversalError):
        ws.resolve_safe_path("../escape.txt")
    with pytest.raises(WorkspacePathTraversalError):
        ws.resolve_safe_path(".dartfx/secret.txt")

    # Quota check on ingest
    with pytest.raises(QuotaExceededError):
        ws.ingest_file(b"x" * 500, "data/too_big.txt", quota_bytes=100)

    # Ingest valid file & verify auto-scan
    entry = ws.ingest_file(b"col1,col2\n1,2\n3,4\n", "data/uploaded.csv")
    assert entry.path == "data/uploaded.csv"
    assert entry.registered is True
    assert entry.file_type == "data"
    assert entry.file_format == "csv"
    assert entry.uuid is not None

    # Resolve download by path and by UUID
    p_by_path, mime1 = ws.resolve_download_path("data/uploaded.csv")
    p_by_uuid, mime2 = ws.resolve_download_path(entry.uuid)
    assert p_by_path == p_by_uuid
    assert mime1 == "text/csv"
    assert mime2 == "text/csv"

    # Archive directory
    zip_path = ws.create_archive("data")
    try:
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            assert "data/sample_survey.csv" in names
            assert "data/uploaded.csv" in names
    finally:
        zip_path.unlink(missing_ok=True)


def test_list_tree_preview_metadata_and_file_ops(tmp_path):
    ws = Space.provision_ephemeral_workspace(tmp_path / "ws")

    entries = ws.list_files(".", recursive=True, type_filter="^data")
    assert len(entries) == 1
    assert entries[0].path == "data/sample_survey.csv"

    tree = ws.get_tree(".")
    assert tree.is_dir is True
    assert any(child.name == "data" for child in tree.children)

    head = ws.preview_file("data/sample_survey.csv", mode="head", num_lines=2)
    assert len(head.lines) == 2
    assert head.lines[0].startswith("respondent_id")

    tail = ws.preview_file("data/sample_survey.csv", mode="tail", num_lines=2)
    assert len(tail.lines) == 2

    detail = ws.get_resource_detail("data/sample_survey.csv")
    assert detail.file_format == "csv"

    updated = ws.update_resource_metadata(detail.uuid, attributes={"curationStatus": "verified"})
    assert updated.attributes["curationStatus"] == "verified"

    turtle = ws.export_rdf(detail.uuid, rdf_format="turtle")
    assert "FileResource" in turtle
    jsonld = json.loads(ws.export_rdf(detail.uuid, rdf_format="json-ld"))
    assert jsonld

    # Move, copy, mkdir, remove
    ws.mkdir("prod/v1")
    ws.copy_path("data/sample_survey.csv", "prod/v1/survey_copy.csv")
    assert (ws.path / "prod/v1/survey_copy.csv").exists()
    ws.move_path("prod/v1/survey_copy.csv", "prod/v1/survey_final.csv")
    assert (ws.path / "prod/v1/survey_final.csv").exists()
    ws.remove_path("prod/v1/survey_final.csv")
    assert not (ws.path / "prod/v1/survey_final.csv").exists()


def test_sparql_and_tabular_queries(tmp_path):
    ws = Space.provision_ephemeral_workspace(tmp_path / "ws")

    sparql = ws.query_sparql(
        """
        PREFIX dartfx: <https://dataartifex.org/workspace/>
        SELECT ?path ?type WHERE {
            ?s a dartfx:FileResource ;
               dartfx:path ?path ;
               dartfx:fileType ?type .
        } ORDER BY ?path
        """
    )
    assert sparql.columns == ["path", "type"]
    assert sparql.row_count == 3

    ask_res = ws.query_sparql("ASK { ?s a <https://dataartifex.org/workspace/FileResource> }")
    assert ask_res.rows == [{"result": "true"}]

    tab = ws.query_tabular("SELECT region, COUNT(*) AS cnt FROM sample_survey GROUP BY region ORDER BY region")
    assert tab.row_count == 4
    assert "region" in tab.columns

    with pytest.raises(ValueError, match="Only read-only SELECT or WITH"):
        ws.query_tabular("DROP TABLE sample_survey")


def test_programmatic_task_runners_and_async_stream(tmp_path):
    ws = Space.provision_ephemeral_workspace(tmp_path / "ws")

    events: list[TaskEvent] = []
    final = run_scan_task(ws, task_id="t-1", workspace_id="ws-1", on_event=events.append)
    assert final.status == TaskStatus.COMPLETED
    assert final.progress_pct == 100.0
    assert any(e.task_type == TaskType.SCAN for e in events)

    async def _collect() -> list[TaskEvent]:
        streamed: list[TaskEvent] = []
        async for ev in stream_task(run_scan_task, ws, task_id="t-2", workspace_id="ws-1"):
            streamed.append(ev)
        return streamed

    streamed_events = asyncio.run(_collect())
    assert streamed_events[-1].status == TaskStatus.COMPLETED

    # Mocked fairify / readstat / tocsv programmatic task tests
    class _Proc:
        def __init__(self):
            self.returncode = 0
            self.stdout = "ok"
            self.stderr = ""

    sav_file = ws.path / "data" / "survey.sav"
    sav_file.write_text("sav-placeholder", encoding="utf-8")

    with (
        patch("dartfx.workspace.tasks.shutil.which", return_value="/usr/bin/mockbin"),
        patch("dartfx.workspace.tasks.subprocess.run", return_value=_Proc()),
    ):
        fairify_ev = run_fairify_task(ws, task_id="t-3", workspace_id="ws-1", source_rel_path="data/sample_survey.csv")
        assert fairify_ev.status == TaskStatus.COMPLETED

        rs_ev = run_readstat_task(
            ws,
            task_id="t-4",
            workspace_id="ws-1",
            source_rel_path="data/survey.sav",
            extract_metadata=True,
        )
        assert rs_ev.status == TaskStatus.COMPLETED

        tocsv_ev = run_tocsv_task(ws, task_id="t-5", workspace_id="ws-1", source_rel_path="data/survey.sav")
        assert tocsv_ev.status == TaskStatus.COMPLETED


def test_system_generated_detection_and_command_applicability(tmp_path):
    from dartfx.workspace.utils import (
        compute_applicable_actions,
        detect_system_generated,
        is_fairifiable_file,
        is_statistical_file,
    )

    # 1. Detection of system-generated artifacts
    assert detect_system_generated("test.stats.csv") == (True, "qsv")
    assert detect_system_generated("test.stats.csv.json") == (True, "qsv")
    assert detect_system_generated("test.stats.csv.data.jsonl") == (True, "qsv")
    assert detect_system_generated("test.freqs.csv") == (True, "qsv")
    assert detect_system_generated("test.freqs.long.csv") == (True, "qsv")
    assert detect_system_generated("test.schema.json") == (True, "qsv")
    assert detect_system_generated("test.description.md") == (True, "qsv")
    assert detect_system_generated("test.csv.idx") == (True, "qsv")
    assert detect_system_generated("test.readstat.json") == (True, "readstat")
    assert detect_system_generated("my_data.csv") == (False, None)
    assert detect_system_generated("survey.dta") == (False, None)

    # 2. Statistical file check
    for ext in ("dta", "por", "sav", "sas7bdat", "xpt", "zsav"):
        assert is_statistical_file(f"file.{ext}") is True
    assert is_statistical_file("file.csv") is False
    assert is_statistical_file("file.parquet") is False

    # 3. Fairifiable file check
    assert is_fairifiable_file("data.csv", is_generated=False) is True
    assert is_fairifiable_file("data.parquet", is_generated=False) is True
    assert is_fairifiable_file("data.csv", is_generated=True) is False
    assert is_fairifiable_file("data.stats.csv", is_generated=False) is False
    assert is_fairifiable_file("data.freqs.csv", is_generated=False) is False
    assert is_fairifiable_file("data.dta", is_generated=False) is False

    # 4. Applicable actions
    user_csv_actions = compute_applicable_actions("data.csv", is_dir=False, is_generated=False)
    assert "fairify" in user_csv_actions
    assert "tocsv" not in user_csv_actions
    assert "preview" in user_csv_actions
    assert "download" in user_csv_actions
    assert "delete" in user_csv_actions

    stats_csv_actions = compute_applicable_actions("data.stats.csv", is_dir=False, is_generated=True)
    assert "fairify" not in stats_csv_actions
    assert "tocsv" not in stats_csv_actions

    stata_actions = compute_applicable_actions("survey.dta", is_dir=False, is_generated=False)
    assert "tocsv" in stata_actions
    assert "readstat" in stata_actions
    assert "fairify" not in stata_actions

    dir_actions = compute_applicable_actions("data", is_dir=True)
    assert dir_actions == ["download", "delete"]

    # 5. Workspace integration and rejecting fairify on system-generated file
    ws = Space.provision_ephemeral_workspace(tmp_path / "ws")
    gen_file = ws.path / "data" / "survey.stats.csv"
    gen_file.write_text("field,type\nfoo,integer\n", encoding="utf-8")
    ws.scanner.scan_path(gen_file, is_generated=True, generated_by="qsv")

    entry = ws.list_files("data/survey.stats.csv")[0]
    assert entry.is_generated is True
    assert entry.generated_by == "qsv"
    assert "fairify" not in entry.applicable_actions

    detail = ws.get_resource_detail("data/survey.stats.csv")
    assert detail.is_generated is True
    assert detail.generated_by == "qsv"
    assert "fairify" not in detail.applicable_actions

    failed_ev = run_fairify_task(ws, task_id="t-fail", workspace_id="ws-1", source_rel_path="data/survey.stats.csv")
    assert failed_ev.status == TaskStatus.FAILED
    assert "Cannot fairify system-generated artifact" in (failed_ev.error or "")

    # 6. Fairify up-to-date detection, stale detection, and force rerun
    from dartfx.workspace.utils import get_fairify_status, is_fairify_up_to_date

    csv_file = ws.path / "data" / "clean.csv"
    csv_file.write_text("a,b\n1,2\n", encoding="utf-8")
    ws.scanner.scan_path(csv_file, is_generated=False)

    assert is_fairify_up_to_date(csv_file) is False
    assert get_fairify_status(csv_file) == "available"
    actions_init = compute_applicable_actions("data/clean.csv", is_dir=False, is_generated=False, full_path=csv_file)
    assert "fairify" in actions_init

    # Create mock artifacts older/newer than source
    import time

    time.sleep(0.05)
    (ws.path / "data" / "clean.csv.stats.csv").write_text("stats", encoding="utf-8")
    (ws.path / "data" / "clean.freqs.csv").write_text("freqs", encoding="utf-8")
    (ws.path / "data" / "clean.csv.schema.json").write_text("schema", encoding="utf-8")

    assert is_fairify_up_to_date(csv_file) is True
    assert get_fairify_status(csv_file) == "up_to_date"
    actions_done = compute_applicable_actions("data/clean.csv", is_dir=False, is_generated=False, full_path=csv_file)
    assert "fairify" not in actions_done

    # Running fairify task without force fails due to up-to-date check
    blocked_ev = run_fairify_task(ws, task_id="t-block", workspace_id="ws-1", source_rel_path="data/clean.csv")
    assert blocked_ev.status == TaskStatus.FAILED
    assert "has already been FAIRified and has not changed" in (blocked_ev.error or "")

    # Running fairify task with force=True succeeds
    with (
        patch("dartfx.workspace.tasks.shutil.which", return_value="/usr/bin/mockbin"),
        patch("dartfx.workspace.tasks.subprocess.run", return_value=_Proc()),
    ):
        forced_ev = run_fairify_task(
            ws, task_id="t-force", workspace_id="ws-1", source_rel_path="data/clean.csv", force=True
        )
        assert forced_ev.status == TaskStatus.COMPLETED

    # Modifying the source makes artifacts stale
    time.sleep(0.05)
    csv_file.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    assert is_fairify_up_to_date(csv_file) is False
    assert get_fairify_status(csv_file) == "stale"
    actions_stale = compute_applicable_actions("data/clean.csv", is_dir=False, is_generated=False, full_path=csv_file)
    assert "fairify" in actions_stale
