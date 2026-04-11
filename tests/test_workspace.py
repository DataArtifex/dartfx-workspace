"""
Unit tests for the Workspace management system.
"""

from pathlib import Path
from dartfx.workspace.core import Workspace
from dartfx.workspace.models import FileType
import pytest
import uuid

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
    assert new_file["uuid"] == orig_uuid # UUID should be preserved!
