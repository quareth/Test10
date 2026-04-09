"""Tests for backend.storage."""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.schemas import PageContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_data_dir(tmp_path: Path) -> Path:
    """Return a temporary DATA_DIR and patch settings to use it."""
    return tmp_path


def _patch_data_dir(tmp_path: Path):
    """Return a patch context manager that overrides _data_dir to tmp_path."""
    return patch("backend.storage._data_dir", return_value=tmp_path)


# ---------------------------------------------------------------------------
# write_snapshot
# ---------------------------------------------------------------------------


class TestWriteSnapshot:
    def test_creates_correct_structure(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import write_snapshot

            pages = [
                PageContent(url="https://example.com/about", url_path="/about", markdown="# About"),
            ]
            rel_path = write_snapshot(
                target_id=1, job_id=10, bulk_content="# Bulk", structured_pages=pages
            )

            snapshot_dir = tmp_path / rel_path
            assert snapshot_dir.exists()
            # bulk.md must exist
            assert (snapshot_dir / "bulk.md").exists()
            assert (snapshot_dir / "bulk.md").read_text(encoding="utf-8") == "# Bulk"
            # structured directory must exist
            assert (snapshot_dir / "structured").is_dir()
            # relative path format: snapshots/{target_id}/{job_id}_{timestamp}
            assert rel_path.startswith("snapshots/1/10_")


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


class TestReadFile:
    def test_returns_bytes(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import read_file

            snap = tmp_path / "snap1"
            snap.mkdir()
            (snap / "file.md").write_bytes(b"hello")
            result = read_file("snap1", "file.md")
            assert result == b"hello"

    def test_blocks_path_traversal(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import read_file

            snap = tmp_path / "snap1"
            snap.mkdir()
            # Create a file outside snapshot dir
            (tmp_path / "secret.txt").write_bytes(b"secret")

            with pytest.raises(ValueError, match="traversal"):
                read_file("snap1", "../secret.txt")

    def test_raises_value_error_for_directory(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import read_file

            snap = tmp_path / "snap1"
            sub = snap / "subdir"
            sub.mkdir(parents=True)

            with pytest.raises(ValueError, match="directory"):
                read_file("snap1", "subdir")

    def test_raises_file_not_found(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import read_file

            snap = tmp_path / "snap1"
            snap.mkdir()

            with pytest.raises(FileNotFoundError):
                read_file("snap1", "nonexistent.md")


# ---------------------------------------------------------------------------
# generate_zip
# ---------------------------------------------------------------------------


class TestGenerateZip:
    def test_bulk_mode(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import generate_zip

            snap = tmp_path / "snap1"
            snap.mkdir()
            (snap / "bulk.md").write_text("# Bulk content", encoding="utf-8")

            buf = generate_zip("snap1", "bulk")
            with zipfile.ZipFile(buf) as zf:
                names = zf.namelist()
                assert "bulk.md" in names
                assert zf.read("bulk.md").decode() == "# Bulk content"

    def test_structured_mode(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import generate_zip

            snap = tmp_path / "snap1"
            structured = snap / "structured"
            structured.mkdir(parents=True)
            (structured / "page.md").write_text("# Page", encoding="utf-8")

            buf = generate_zip("snap1", "structured")
            with zipfile.ZipFile(buf) as zf:
                names = zf.namelist()
                assert any("page.md" in n for n in names)


# ---------------------------------------------------------------------------
# list_snapshot_files
# ---------------------------------------------------------------------------


class TestListSnapshotFiles:
    def test_returns_correct_paths(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import list_snapshot_files

            snap = tmp_path / "snap1"
            snap.mkdir()
            (snap / "bulk.md").write_text("bulk", encoding="utf-8")
            structured = snap / "structured"
            structured.mkdir()
            (structured / "page.md").write_text("page", encoding="utf-8")

            files = list_snapshot_files("snap1")
            assert "bulk.md" in files
            assert os.path.join("structured", "page.md") in files

    def test_returns_empty_for_missing_dir(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import list_snapshot_files

            files = list_snapshot_files("nonexistent")
            assert files == []


# ---------------------------------------------------------------------------
# delete_snapshot_files
# ---------------------------------------------------------------------------


class TestDeleteSnapshotFiles:
    def test_removes_tree(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import delete_snapshot_files

            snap = tmp_path / "snap1"
            snap.mkdir()
            (snap / "file.md").write_text("data", encoding="utf-8")

            delete_snapshot_files("snap1")
            assert not snap.exists()

    def test_noop_for_missing_dir(self, tmp_path: Path):
        with _patch_data_dir(tmp_path):
            from backend.storage import delete_snapshot_files

            # Should not raise
            delete_snapshot_files("nonexistent")
