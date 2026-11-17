from pathlib import Path
from unittest.mock import MagicMock

import pytest
import typer

from dartfx.workspace.core import Workspace
from dartfx.workspace.shell import (
    ShellContext,
    handle_about,
    handle_bang_command,
    handle_fairify,
    handle_help,
    handle_init,
    handle_ls,
    handle_qsv_command,
    handle_readstat,
    handle_scan,
    handle_tocsv,
    handle_tree,
    resolve_shell_workspace,
)


def test_shell_handlers_imports_and_symbols(tmp_path):
    """
    Smoke test to ensure shell handlers don't crash due to NameError or missing imports.
    This would have caught the missing 'Tree' import.
    """
    # Mock Workspace
    mock_ws = MagicMock()
    mock_ws.path = tmp_path
    mock_ws.is_initialized.return_value = True
    mock_ws.kb.get_all_files.return_value = []

    # Mock specific KB lookups needed for handle_about
    mock_ws.kb.get_file_by_path.return_value = {
        "path": "dummy/subdir/resource.csv",
        "uuid": "550e8400-e29b-41d4-a716-446655440000",
        "type": "data/csv",
        "file_format": "csv",
        "mime_type": "text/csv",
        "size_bytes": 1024,
        "blake3_hash": "abc",
        "created_at": "2024-01-01",
        "updated_at": "2024-01-01",
    }
    mock_ws.kb.get_resource_attributes.return_value = {}
    mock_ws.dartfx_dir = tmp_path / ".dartfx"

    # Mock ShellContext
    ctx = ShellContext(mock_ws)
    ctx.cwd = tmp_path

    # We use a dummy directory to avoid real IO issues,
    # but the primary goal is symbol resolution.
    dummy_dir = tmp_path / "dummy"
    dummy_dir.mkdir()
    (dummy_dir / "file.txt").touch()

    # Test handlers - should NOT crash
    try:
        # Test tree with various filters
        handle_tree(ctx, [str(dummy_dir), "--format", "parquet"])
        handle_tree(ctx, ["--uuid", "-L", "2"])

        # Test ls with various flags (exercises hidden file filtering)
        handle_ls(ctx, [str(dummy_dir), "--mime", "application/pdf"])
        handle_ls(ctx, ["--all"])
        handle_ls(ctx, ["-R"])

        # Test about
        (dummy_dir / "subdir").mkdir()
        (dummy_dir / "subdir" / "resource.csv").touch()
        handle_about(ctx, [str(dummy_dir / "subdir" / "resource.csv")])

        # Test help
        handle_help(ctx, [])

    except (NameError, UnboundLocalError) as e:
        pytest.fail(f"Shell handler failed with Name/Unbound Error (missing import or init): {e}")
    except Exception as e:
        # We fail on any unexpected exception in our handlers
        pytest.fail(f"Shell handler crashed with unexpected error: {type(e).__name__}: {e}")


def test_type_label_helper():
    """Test the reusable type label helper introduced for filtering."""
    from dartfx.workspace.shell import _get_type_label

    assert _get_type_label(None) == "-"
    assert _get_type_label({"type": "data"}) == "data"
    assert _get_type_label({"type": "data", "file_format": "csv"}) == "data/csv"
    assert _get_type_label({"type": "data", "file_format": "undetermined"}) == "data"


def test_resolve_shell_workspace_falls_back_to_parent(tmp_path):
    root = tmp_path / "root"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    Workspace.init(root)

    ws, cwd = resolve_shell_workspace(nested)
    assert ws.path == root.resolve()
    assert cwd == nested.resolve()


def test_handle_init_rejects_nested_workspace(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    Workspace.init(parent)

    ctx = ShellContext(Workspace(child))

    messages: list[str] = []

    def fake_secho(message: str, *args, **kwargs):
        messages.append(message)

    monkeypatch.setattr(typer, "secho", fake_secho)

    handle_init(ctx, [])

    assert not (child / ".dartfx").exists()
    assert any("cannot initialize nested workspace" in msg for msg in messages)


def test_handle_scan_refresh_alias_wipes_and_scans(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path)
    ctx = ShellContext(ws)

    wiped = {"called": False}
    scanned: list[Path | None] = []

    monkeypatch.setattr(typer, "confirm", lambda _msg: True)
    monkeypatch.setattr(ws.kb, "wipe", lambda: wiped.__setitem__("called", True))

    def fake_scan(target_path=None, **_kwargs):
        scanned.append(target_path)

    monkeypatch.setattr(ws.scanner, "scan", fake_scan)

    handle_scan(ctx, ["--refresh", "."])

    assert wiped["called"] is True
    assert scanned
    assert scanned[0] == tmp_path.resolve()


def test_handle_readstat_shows_usage_without_args(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    output: list[str] = []

    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: "/usr/local/bin/readstat")
    monkeypatch.setattr(typer, "echo", lambda msg: output.append(msg))

    handle_readstat(ctx, [])

    assert output
    assert output[0] == "ReadStat proxy usage:"


def test_handle_readstat_forwards_to_subprocess_with_resolved_paths(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    called: dict[str, object] = {}

    class _Result:
        returncode = 0

    def fake_run(cmd, cwd, check):
        called["cmd"] = cmd
        called["cwd"] = cwd
        called["check"] = check
        return _Result()

    # When no --metadata flag, should use readstat
    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: "/usr/local/bin/readstat")
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)

    handle_readstat(ctx, ["in.sav", "-"])

    assert called["cmd"] == ["/usr/local/bin/readstat", str((tmp_path / "in.sav").resolve()), "-"]
    assert called["cwd"] == tmp_path
    assert called["check"] is False


def test_handle_readstat_preserves_absolute_paths(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    called: dict[str, object] = {}

    class _Result:
        returncode = 0

    absolute_input = (tmp_path.parent / "input.sav").resolve()
    absolute_output = (tmp_path.parent / "output.csv").resolve()

    def fake_run(cmd, cwd, check):
        called["cmd"] = cmd
        called["cwd"] = cwd
        called["check"] = check
        return _Result()

    # When no --metadata flag, should use readstat for conversion
    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: "/usr/local/bin/readstat")
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)

    handle_readstat(ctx, [str(absolute_input), str(absolute_output)])

    assert called["cmd"] == ["/usr/local/bin/readstat", str(absolute_input), str(absolute_output)]
    assert called["cwd"] == tmp_path
    assert called["check"] is False


def test_handle_readstat_forwards_metadata_flag_and_registers_output(tmp_path, monkeypatch):
    """Test readstat --metadata <input> <output> calls extract_metadata."""
    ws = Workspace.init(tmp_path)
    ctx = ShellContext(ws)

    in_file = tmp_path / "survey.sav"
    meta_file = tmp_path / "survey.sav.json"
    in_file.write_text("input")
    meta_file.write_text('{"metadata": "output"}')

    class _Result:
        returncode = 0

    registered: list[Path] = []

    def fake_run(*args, **kwargs):
        # Simulate extract_metadata creating/updating output file
        meta_file.write_text('{"new": "metadata"}')
        return _Result()

    # With --metadata flag, should use extract_metadata
    monkeypatch.setattr(
        "dartfx.workspace.shell.shutil.which",
        lambda bin: "/usr/local/bin/extract_metadata" if bin == "extract_metadata" else "/usr/local/bin/readstat",
    )
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)
    monkeypatch.setattr(ws.scanner, "scan_path", lambda p: registered.append(p))

    # Test with --metadata flag and explicit output (using --force since file already exists)
    handle_readstat(ctx, ["--force", "--metadata", "survey.sav", "survey.sav.json"])

    assert registered == [meta_file.resolve()]


def test_handle_readstat_metadata_with_explicit_output(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path)
    ctx = ShellContext(ws)

    in_file = tmp_path / "survey.sav"
    custom_meta = tmp_path / "custom_metadata.json"
    in_file.write_text("input")
    custom_meta.write_text('{"metadata": "output"}')

    class _Result:
        returncode = 0

    registered: list[Path] = []

    def fake_run(*args, **kwargs):
        # Simulate extract_metadata creating/updating output file
        custom_meta.write_text('{"new": "metadata"}')
        return _Result()

    # With --metadata flag, should use extract_metadata
    monkeypatch.setattr(
        "dartfx.workspace.shell.shutil.which",
        lambda bin: "/usr/local/bin/extract_metadata" if bin == "extract_metadata" else "/usr/local/bin/readstat",
    )
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)
    monkeypatch.setattr(ws.scanner, "scan_path", lambda p: registered.append(p))

    # Test explicit output filename with --metadata flag
    handle_readstat(ctx, ["--force", "--metadata", "survey.sav", "custom_metadata.json"])

    assert registered == [custom_meta.resolve()]


def test_handle_readstat_metadata_auto_generates_output(tmp_path, monkeypatch):
    """Test readstat --metadata <input> auto-generates <input>.readstat.json."""
    ws = Workspace.init(tmp_path)
    ctx = ShellContext(ws)

    in_file = tmp_path / "survey.sav"
    meta_file = tmp_path / "survey.sav.readstat.json"
    in_file.write_text("input")
    meta_file.write_text('{"metadata": "output"}')

    class _Result:
        returncode = 0

    registered: list[Path] = []

    def fake_run(*args, **kwargs):
        # Simulate extract_metadata creating/updating output file
        meta_file.write_text('{"new": "metadata"}')
        return _Result()

    # With --metadata flag, should use extract_metadata
    monkeypatch.setattr(
        "dartfx.workspace.shell.shutil.which",
        lambda bin: "/usr/local/bin/extract_metadata" if bin == "extract_metadata" else "/usr/local/bin/readstat",
    )
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)
    monkeypatch.setattr(ws.scanner, "scan_path", lambda p: registered.append(p))

    # Test with --metadata but no explicit output (should auto-generate)
    handle_readstat(ctx, ["--force", "--metadata", "survey.sav"])

    assert registered == [meta_file.resolve()]


def test_handle_readstat_metadata_requires_force_to_overwrite(tmp_path, monkeypatch):
    """Test readstat --metadata requires --force to overwrite existing file."""
    ws = Workspace.init(tmp_path)
    ctx = ShellContext(ws)

    in_file = tmp_path / "survey.sav"
    meta_file = tmp_path / "survey.sav.readstat.json"
    in_file.write_text("input")
    # Create existing metadata file
    meta_file.write_text('{"old": "metadata"}')

    class _Result:
        returncode = 0

    messages: list[str] = []

    monkeypatch.setattr(
        "dartfx.workspace.shell.shutil.which",
        lambda bin: "/usr/local/bin/extract_metadata" if bin == "extract_metadata" else "/usr/local/bin/readstat",
    )
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", lambda *_args, **_kwargs: _Result())
    monkeypatch.setattr(typer, "secho", lambda msg, *args, **kwargs: messages.append(msg))

    # Try without --force (should fail)
    handle_readstat(ctx, ["--metadata", "survey.sav"])

    # Should have error message
    assert any("already exists" in msg for msg in messages)


def test_handle_readstat_metadata_force_overwrites_existing(tmp_path, monkeypatch):
    """Test readstat --metadata --force overwrites existing metadata file."""
    ws = Workspace.init(tmp_path)
    ctx = ShellContext(ws)

    in_file = tmp_path / "survey.sav"
    meta_file = tmp_path / "survey.sav.readstat.json"
    in_file.write_text("input")
    # Create existing metadata file with old content
    meta_file.write_text('{"old": "metadata"}')
    old_mtime = meta_file.stat().st_mtime

    class _Result:
        returncode = 0

    registered: list[Path] = []

    def fake_run(*args, **kwargs):
        # Simulate extract_metadata creating new file with new content
        import time

        time.sleep(0.01)  # Ensure mtime differs
        meta_file.write_text('{"new": "metadata"}')
        return _Result()

    monkeypatch.setattr(
        "dartfx.workspace.shell.shutil.which",
        lambda bin: "/usr/local/bin/extract_metadata" if bin == "extract_metadata" else "/usr/local/bin/readstat",
    )
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)
    monkeypatch.setattr(ws.scanner, "scan_path", lambda p: registered.append(p))

    # With --force (should succeed)
    handle_readstat(ctx, ["--force", "--metadata", "survey.sav"])

    # Should have overwritten the file (new content)
    assert meta_file.read_text() == '{"new": "metadata"}'
    assert meta_file.stat().st_mtime > old_mtime
    assert registered == [meta_file.resolve()]


def test_handle_readstat_metadata_subprocess_args(tmp_path, monkeypatch):
    """Verify that --metadata calls extract_metadata with correct args."""
    ws = Workspace.init(tmp_path)
    ctx = ShellContext(ws)

    in_file = tmp_path / "survey.sav"
    meta_file = tmp_path / "survey.sav.json"
    in_file.write_text("input")
    meta_file.write_text('{"metadata": "output"}')

    class _Result:
        returncode = 0

    captured_cmd = None

    def fake_run(cmd, *args, **kwargs):
        nonlocal captured_cmd
        captured_cmd = cmd
        return _Result()

    monkeypatch.setattr(
        "dartfx.workspace.shell.shutil.which",
        lambda bin: "/usr/local/bin/extract_metadata" if bin == "extract_metadata" else "/usr/local/bin/readstat",
    )
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)
    monkeypatch.setattr(ws.scanner, "scan_path", lambda _p: None)

    # Call with --metadata flag
    handle_readstat(ctx, ["--force", "--metadata", "survey.sav", "survey.sav.json"])

    # Verify extract_metadata was called with correct args
    assert captured_cmd is not None
    assert captured_cmd[0] == "/usr/local/bin/extract_metadata"
    assert any("survey.sav" in str(arg) for arg in captured_cmd)
    assert any("survey.sav.json" in str(arg) for arg in captured_cmd)


def test_handle_readstat_errors_when_binary_missing(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    messages: list[str] = []

    # Both readstat and extract_metadata are missing
    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: None)
    monkeypatch.setattr(typer, "secho", lambda msg, *args, **kwargs: messages.append(msg))

    # Test view case (no --metadata, no output) - should try readstat
    handle_readstat(ctx, ["input.sav"])

    assert any("readstat" in msg and "command not found" in msg for msg in messages)


def test_handle_readstat_registers_output_file_on_success(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path)
    ctx = ShellContext(ws)

    in_file = tmp_path / "in.sav"
    out_file = tmp_path / "out.csv"
    in_file.write_text("input")
    out_file.write_text("output")

    class _Result:
        returncode = 0

    registered: list[Path] = []

    # No --metadata, so should use readstat for conversion
    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: "/usr/local/bin/readstat")
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", lambda *_args, **_kwargs: _Result())
    monkeypatch.setattr(ws.scanner, "scan_path", lambda p: registered.append(p))

    handle_readstat(ctx, ["in.sav", "out.csv"])

    assert registered == [out_file.resolve()]


def test_handle_readstat_does_not_register_stdout_or_failure(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path)
    ctx = ShellContext(ws)

    class _ResultOk:
        returncode = 0

    class _ResultFail:
        returncode = 2

    registered: list[Path] = []

    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: "/usr/local/bin/readstat")
    monkeypatch.setattr(ws.scanner, "scan_path", lambda p: registered.append(p))

    # Stdout case: should not register
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", lambda *_args, **_kwargs: _ResultOk())
    handle_readstat(ctx, ["in.sav", "-"])

    # Failure case: should not register
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", lambda *_args, **_kwargs: _ResultFail())
    handle_readstat(ctx, ["in.sav", "out.csv"])

    assert registered == []


def test_handle_tocsv_delegates_to_readstat_with_csv_target(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    src = tmp_path / "survey.sav"
    src.write_text("input")

    delegated: list[list[str]] = []
    monkeypatch.setattr("dartfx.workspace.shell.handle_readstat", lambda _ctx, argv: delegated.append(argv))

    handle_tocsv(ctx, ["survey.sav"])

    assert delegated == [[str(src.resolve()), str((tmp_path / "survey.csv").resolve())]]


def test_handle_tocsv_rejects_unsupported_extensions(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    src = tmp_path / "notes.txt"
    src.write_text("input")

    messages: list[str] = []
    monkeypatch.setattr(typer, "secho", lambda msg, *args, **kwargs: messages.append(msg))

    handle_tocsv(ctx, ["notes.txt"])

    assert any("unsupported source type" in msg for msg in messages)


def test_handle_tocsv_requires_force_when_target_exists(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    src = tmp_path / "sample.dta"
    dst = tmp_path / "sample.csv"
    src.write_text("input")
    dst.write_text("existing")

    delegated: list[list[str]] = []
    messages: list[str] = []
    monkeypatch.setattr("dartfx.workspace.shell.handle_readstat", lambda _ctx, argv: delegated.append(argv))
    monkeypatch.setattr(typer, "secho", lambda msg, *args, **kwargs: messages.append(msg))

    handle_tocsv(ctx, ["sample.dta"])

    assert delegated == []
    assert dst.exists()
    assert any("target already exists" in msg for msg in messages)


def test_handle_tocsv_force_overwrites_and_delegates(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    src = tmp_path / "sample.dta"
    dst = tmp_path / "sample.csv"
    src.write_text("input")
    dst.write_text("existing")

    delegated: list[list[str]] = []
    monkeypatch.setattr("dartfx.workspace.shell.handle_readstat", lambda _ctx, argv: delegated.append(argv))

    handle_tocsv(ctx, ["--force", "sample.dta"])

    assert delegated == [[str(src.resolve()), str(dst.resolve())]]


def test_handle_bang_command_runs_in_current_directory(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    called: dict[str, object] = {}

    class _Result:
        returncode = 0

    def fake_run(cmd, cwd, check, shell):
        called["cmd"] = cmd
        called["cwd"] = cwd
        called["check"] = check
        called["shell"] = shell
        return _Result()

    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)

    handle_bang_command(ctx, "!ls -la")

    assert called["cmd"] == "ls -la"
    assert called["cwd"] == tmp_path
    assert called["check"] is False
    assert called["shell"] is True


def test_handle_bang_command_errors_for_missing_command(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    messages: list[str] = []
    monkeypatch.setattr(typer, "secho", lambda msg, *args, **kwargs: messages.append(msg))

    handle_bang_command(ctx, "!")

    assert any("missing" in msg.lower() for msg in messages)


def test_handle_fairify_rejects_unsupported_type(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    source = tmp_path / "data.json"
    source.write_text("{}")

    messages: list[str] = []
    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: "/usr/local/bin/qsv")
    monkeypatch.setattr(typer, "secho", lambda msg, *args, **kwargs: messages.append(msg))

    handle_fairify(ctx, ["data.json"])

    assert any("unsupported source type" in msg for msg in messages)


def test_handle_fairify_requires_gemini_key_for_describe(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    source = tmp_path / "data.csv"
    source.write_text("a,b\n1,2\n")

    messages: list[str] = []
    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: "/usr/local/bin/qsv")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(typer, "secho", lambda msg, *args, **kwargs: messages.append(msg))

    handle_fairify(ctx, ["data.csv", "--describe"])

    assert any("GEMINI_API_KEY" in msg for msg in messages)


def test_handle_fairify_runs_bundle_and_registers_outputs(tmp_path, monkeypatch):
    ws = Workspace.init(tmp_path)
    ctx = ShellContext(ws)

    source = tmp_path / "person.csv"
    source.write_text("a,b\n1,2\n")

    registered: list[Path] = []
    called: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run(cmd, *args, **kwargs):
        called.append(cmd)
        if cmd[1] == "index":
            source.with_name(f"{source.name}.idx").write_text("idx")
        if cmd[1] == "stats":
            (tmp_path / "person.csv.stats.csv").write_text("stats")
            (tmp_path / "person.csv.stats.csv.data.jsonl").write_text("stats_data")
            (tmp_path / "person.csv.stats.csv.json").write_text("stats_json")
        if cmd[1] == "schema":
            (tmp_path / "person.csv.schema.json").write_text("schema")
        if cmd[1] == "frequency":
            (tmp_path / "person.freqs.csv").write_text("freq")
        if cmd[1] == "transpose":
            (tmp_path / "person.freqs.long.csv").write_text("freq_long")
        return _Result()

    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: "/usr/local/bin/qsv")
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)
    monkeypatch.setattr(ws.scanner, "scan_path", lambda p: registered.append(p))

    handle_fairify(ctx, ["person.csv"])

    assert [cmd[1] for cmd in called] == ["index", "stats", "moarstats", "schema", "frequency", "transpose"]
    assert registered == [
        (tmp_path / "person.csv.idx").resolve(),
        (tmp_path / "person.csv.schema.json").resolve(),
        (tmp_path / "person.csv.stats.csv").resolve(),
        (tmp_path / "person.csv.stats.csv.data.jsonl").resolve(),
        (tmp_path / "person.csv.stats.csv.json").resolve(),
        (tmp_path / "person.freqs.csv").resolve(),
        (tmp_path / "person.freqs.long.csv").resolve(),
    ]


def test_handle_fairify_skips_describegpt_when_output_up_to_date(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    source = tmp_path / "person.csv"
    source.write_text("a,b\n1,2\n")

    # Make description newer than source to mark it up-to-date.
    import time

    time.sleep(0.01)
    (tmp_path / "person.description.md").write_text("up-to-date")

    called: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run(cmd, *args, **kwargs):
        called.append(cmd)
        return _Result()

    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: "/usr/local/bin/qsv")
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    handle_fairify(ctx, ["person.csv", "--describe"])

    assert "describegpt" not in [cmd[1] for cmd in called]


def test_handle_fairify_runs_describegpt_when_output_outdated(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    source = tmp_path / "person.csv"
    source.write_text("a,b\n1,2\n")

    description = tmp_path / "person.description.md"
    description.write_text("old")

    # Make source newer than description to mark output outdated.
    import time

    time.sleep(0.01)
    source.write_text("a,b\n1,2\n3,4\n")

    called: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run(cmd, *args, **kwargs):
        called.append(cmd)
        return _Result()

    monkeypatch.setattr("dartfx.workspace.shell.shutil.which", lambda _: "/usr/local/bin/qsv")
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    handle_fairify(ctx, ["person.csv", "--describe"])

    assert "describegpt" in [cmd[1] for cmd in called]
    describe_cmd = next(cmd for cmd in called if len(cmd) > 1 and cmd[1] == "describegpt")
    assert "--quiet" in describe_cmd


def test_handle_qsv_command_returns_false_on_nonzero_exit(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    class _Result:
        returncode = 2

    messages: list[str] = []
    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", lambda *_args, **_kwargs: _Result())
    monkeypatch.setattr(typer, "secho", lambda msg, *args, **kwargs: messages.append(msg))

    ok = handle_qsv_command(ctx, [["qsv", "stats", "x.csv"]], command_name="fairify")

    assert ok is False
    assert any("step failed" in msg for msg in messages)


def test_handle_qsv_command_runs_all_steps_on_success(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ctx = ShellContext(ws)

    called: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run(cmd, *args, **kwargs):
        called.append(cmd)
        return _Result()

    monkeypatch.setattr("dartfx.workspace.shell.subprocess.run", fake_run)

    ok = handle_qsv_command(
        ctx,
        [["qsv", "index", "x.csv"], ["qsv", "stats", "x.csv"]],
        command_name="fairify",
    )

    assert ok is True
    assert [cmd[1] for cmd in called] == ["index", "stats"]
