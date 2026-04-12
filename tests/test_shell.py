from unittest.mock import MagicMock

import pytest

from dartfx.workspace.shell import ShellContext, handle_about, handle_help, handle_ls, handle_tree


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
