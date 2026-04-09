"""Filesystem storage service for snapshot management."""

from __future__ import annotations

import io
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from backend.config import settings
from backend.schemas import PageContent
from backend.scraping.indexer import assemble_structured


def _data_dir() -> Path:
    """Return the resolved DATA_DIR as a Path."""
    return Path(settings.DATA_DIR).resolve()


def write_snapshot(
    target_id: int,
    job_id: int,
    bulk_content: str,
    structured_pages: list[PageContent],
) -> str:
    """Write snapshot files to disk and return the relative path from DATA_DIR.

    Creates:
        {DATA_DIR}/snapshots/{target_id}/{job_id}_{iso_timestamp}/
            bulk.md
            structured/
                ...individual .md files...
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dir_name = f"{job_id}_{timestamp}"
    relative_path = f"snapshots/{target_id}/{dir_name}"

    snapshot_dir = _data_dir() / relative_path
    os.makedirs(snapshot_dir, exist_ok=True)

    # Write bulk.md
    bulk_file = snapshot_dir / "bulk.md"
    bulk_file.write_text(bulk_content, encoding="utf-8")

    # Write structured files via indexer
    assemble_structured(structured_pages, snapshot_dir)

    return relative_path


def _resolve_snapshot_dir(snapshot_path: str) -> Path:
    """Resolve a snapshot path relative to DATA_DIR, returning the absolute directory."""
    return _data_dir() / snapshot_path


def read_file(snapshot_path: str, relative_path: str) -> bytes:
    """Read a file from a snapshot directory.

    Validates that relative_path does not escape the snapshot directory.
    Raises ValueError on path traversal attempts.
    Raises FileNotFoundError if the file does not exist.
    """
    snapshot_dir = _resolve_snapshot_dir(snapshot_path).resolve()
    target = (snapshot_dir / relative_path).resolve()

    # Path traversal check: target must be inside snapshot_dir
    if not str(target).startswith(str(snapshot_dir) + os.sep) and target != snapshot_dir:
        raise ValueError(
            f"Path traversal detected: '{relative_path}' escapes snapshot directory"
        )

    # Directory-as-target check
    if target.is_dir():
        raise ValueError(
            f"Path is a directory, not a file: '{relative_path}'"
        )

    return target.read_bytes()


def generate_zip(
    snapshot_path: str, mode: Literal["bulk", "structured", "all"]
) -> io.BytesIO:
    """Generate a zip archive of snapshot files.

    Modes:
        bulk: zip just bulk.md
        structured: zip the structured/ directory
        all: zip everything in the snapshot directory
    """
    snapshot_dir = _resolve_snapshot_dir(snapshot_path)
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if mode == "bulk":
            bulk_file = snapshot_dir / "bulk.md"
            if bulk_file.exists():
                zf.write(bulk_file, "bulk.md")
        elif mode == "structured":
            structured_dir = snapshot_dir / "structured"
            if structured_dir.exists():
                for file_path in sorted(structured_dir.rglob("*")):
                    if file_path.is_file():
                        arcname = str(file_path.relative_to(snapshot_dir))
                        zf.write(file_path, arcname)
        elif mode == "all":
            for file_path in sorted(snapshot_dir.rglob("*")):
                if file_path.is_file():
                    arcname = str(file_path.relative_to(snapshot_dir))
                    zf.write(file_path, arcname)

    buf.seek(0)
    return buf


def list_snapshot_files(snapshot_path: str) -> list[str]:
    """List all files in a snapshot directory as relative paths."""
    snapshot_dir = _resolve_snapshot_dir(snapshot_path)
    if not snapshot_dir.exists():
        return []

    result: list[str] = []
    for file_path in sorted(snapshot_dir.rglob("*")):
        if file_path.is_file():
            result.append(str(file_path.relative_to(snapshot_dir)))
    return result


def delete_snapshot_files(snapshot_path: str) -> None:
    """Remove the snapshot directory tree from disk."""
    snapshot_dir = _resolve_snapshot_dir(snapshot_path)
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
