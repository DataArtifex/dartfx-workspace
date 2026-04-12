from unittest.mock import MagicMock

import pytest

from dartfx.workspace.shell import ShellContext, handle_help, handle_ls, handle_tree


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

    # Mock ShellContext
    ctx = ShellContext(mock_ws)
    ctx.cwd = tmp_path

    # We use a dummy directory to avoid real IO issues,
    # but the primary goal is symbol resolution.
    dummy_dir = tmp_path / "dummy"
    dummy_dir.mkdir()
    (dummy_dir / "file.txt").touch()

    # Test handlers - should NOT raise NameError
    try:
        # Test tree
        handle_tree(ctx, [str(dummy_dir)])

        # Test ls
        handle_ls(ctx, [str(dummy_dir)])

        # Test help
        handle_help(ctx, [])

    except NameError as e:
        pytest.fail(f"Shell handler failed with NameError (likely missing import): {e}")
    except Exception:
        # Other exceptions are okay in this smoke test (e.g. Typer Exit),
        # but NameError is what we are hunting.
        pass


def test_type_label_helper():
    """Test the reusable type label helper introduced for filtering."""
    from dartfx.workspace.shell import _get_type_label

    assert _get_type_label(None) == "-"
    assert _get_type_label({"type": "data"}) == "data"
    assert _get_type_label({"type": "data", "file_format": "csv"}) == "data/csv"
    assert _get_type_label({"type": "data", "file_format": "undetermined"}) == "data"
