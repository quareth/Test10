"""Tests for backend.routes.jobs -- job listing, status, snapshot, and download."""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_user(id_: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=id_, username="testuser")


def _make_target(id_: int = 1, user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_, user_id=user_id, url="https://example.com", name="Example",
        created_at=datetime.now(timezone.utc),
    )


def _make_job(
    id_: int = 10, target_id: int = 1, status: str = "complete",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_, target_id=target_id, status=status,
        pages_found=5, pages_scraped=5,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        error_message=None,
    )


def _make_snapshot(id_: int = 100, job_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_, job_id=job_id, storage_path="snapshots/1/10_20260101T000000",
        file_count=3, total_size_bytes=1024,
        created_at=datetime.now(timezone.utc),
    )


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None


def _make_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# GET /api/targets/{target_id}/jobs -- list_jobs
# ---------------------------------------------------------------------------


class TestListJobs:
    def test_returns_ordered_list(self):
        from backend.routes.jobs import list_jobs

        user = _make_user()
        target = _make_target()
        job1 = _make_job(id_=10)
        job2 = _make_job(id_=11)
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),           # ownership check
            FakeScalarResult([job2, job1]),         # jobs (desc order)
        ])

        result = _run(list_jobs(target_id=1, user=user, db=db))
        assert "jobs" in result
        assert len(result["jobs"]) == 2
        assert result["jobs"][0].id == 11
        assert result["jobs"][1].id == 10


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/status -- get_job_status
# ---------------------------------------------------------------------------


class TestGetJobStatus:
    def test_returns_status(self):
        from backend.routes.jobs import get_job_status

        user = _make_user()
        target = _make_target()
        job = _make_job(status="running")
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([job]),       # job lookup
            FakeScalarResult([target]),     # ownership check
        ])

        result = _run(get_job_status(job_id=10, user=user, db=db))
        assert result["job"].status == "running"


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/snapshot -- get_job_snapshot
# ---------------------------------------------------------------------------


class TestGetJobSnapshot:
    def test_returns_metadata(self):
        from backend.routes.jobs import get_job_snapshot

        user = _make_user()
        target = _make_target()
        job = _make_job()
        snapshot = _make_snapshot()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([job]),        # job lookup
            FakeScalarResult([target]),      # ownership check
            FakeScalarResult([snapshot]),    # snapshot lookup
        ])

        with patch("backend.routes.jobs.list_snapshot_files", return_value=["bulk.md", "structured/page.md"]):
            result = _run(get_job_snapshot(job_id=10, user=user, db=db))

        assert "snapshot" in result
        assert result["snapshot"].id == snapshot.id
        assert "files" in result
        assert len(result["files"]) == 2

    def test_returns_404_if_no_snapshot(self):
        from backend.routes.jobs import get_job_snapshot
        from fastapi import HTTPException

        user = _make_user()
        target = _make_target()
        job = _make_job()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([job]),        # job lookup
            FakeScalarResult([target]),      # ownership check
            FakeScalarResult([]),            # snapshot lookup (none)
        ])

        with pytest.raises(HTTPException) as exc_info:
            _run(get_job_snapshot(job_id=10, user=user, db=db))
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/snapshots/{snapshot_id}/download -- download_snapshot
# ---------------------------------------------------------------------------


class TestDownloadSnapshot:
    def test_bulk_format_content_type(self):
        from backend.routes.jobs import download_snapshot

        user = _make_user()
        target = _make_target()
        job = _make_job()
        snapshot = _make_snapshot()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([snapshot]),    # snapshot lookup
            FakeScalarResult([job]),          # job lookup
            FakeScalarResult([target]),       # ownership check
        ])

        with patch("backend.routes.jobs.read_file", return_value=b"# Bulk content"):
            response = _run(download_snapshot(
                snapshot_id=100, format="bulk", path=None, user=user, db=db
            ))

        assert response.media_type == "application/octet-stream"
        assert response.body == b"# Bulk content"

    def test_structured_zip_format(self):
        from backend.routes.jobs import download_snapshot

        user = _make_user()
        target = _make_target()
        job = _make_job()
        snapshot = _make_snapshot()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([snapshot]),
            FakeScalarResult([job]),
            FakeScalarResult([target]),
        ])

        fake_zip = io.BytesIO(b"PK fake zip data")
        with patch("backend.routes.jobs.generate_zip", return_value=fake_zip):
            response = _run(download_snapshot(
                snapshot_id=100, format="structured_zip", path=None, user=user, db=db
            ))

        assert response.media_type == "application/zip"

    def test_file_format_content_type(self):
        from backend.routes.jobs import download_snapshot

        user = _make_user()
        target = _make_target()
        job = _make_job()
        snapshot = _make_snapshot()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([snapshot]),
            FakeScalarResult([job]),
            FakeScalarResult([target]),
        ])

        with patch("backend.routes.jobs.read_file", return_value=b"# Page content"):
            response = _run(download_snapshot(
                snapshot_id=100, format="file", path="structured/page.md", user=user, db=db
            ))

        assert response.media_type == "application/octet-stream"
        assert response.body == b"# Page content"

    def test_file_format_requires_path(self):
        from backend.routes.jobs import download_snapshot
        from fastapi import HTTPException

        user = _make_user()
        target = _make_target()
        job = _make_job()
        snapshot = _make_snapshot()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([snapshot]),
            FakeScalarResult([job]),
            FakeScalarResult([target]),
        ])

        with pytest.raises(HTTPException) as exc_info:
            _run(download_snapshot(
                snapshot_id=100, format="file", path=None, user=user, db=db
            ))
        assert exc_info.value.status_code == 400

    def test_snapshot_not_found_404(self):
        from backend.routes.jobs import download_snapshot
        from fastapi import HTTPException

        user = _make_user()
        db = _make_db()
        db.execute = AsyncMock(return_value=FakeScalarResult([]))

        with pytest.raises(HTTPException) as exc_info:
            _run(download_snapshot(
                snapshot_id=999, format="bulk", path=None, user=user, db=db
            ))
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Stale running job correction on read
# ---------------------------------------------------------------------------


def _make_stale_job(id_: int = 10, target_id: int = 1) -> SimpleNamespace:
    """Create a running job that started more than 1 hour ago."""
    return SimpleNamespace(
        id=id_, target_id=target_id, status="running",
        pages_found=5, pages_scraped=0,
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        completed_at=None, error_message=None,
    )


class TestStaleJobCorrectionOnRead:
    def test_list_jobs_corrects_stale_running(self):
        from backend.routes.jobs import list_jobs

        user = _make_user()
        target = _make_target()
        stale = _make_stale_job()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),   # ownership check
            FakeScalarResult([stale]),    # jobs list
        ])

        result = _run(list_jobs(target_id=1, user=user, db=db))
        assert result["jobs"][0].status == "failed"
        assert result["jobs"][0].error_message == "Job timed out"
        db.commit.assert_called()

    def test_list_jobs_does_not_touch_fresh_running(self):
        from backend.routes.jobs import list_jobs

        user = _make_user()
        target = _make_target()
        fresh = _make_job(status="running")
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),
            FakeScalarResult([fresh]),
        ])

        result = _run(list_jobs(target_id=1, user=user, db=db))
        assert result["jobs"][0].status == "running"

    def test_get_job_status_corrects_stale(self):
        from backend.routes.jobs import get_job_status

        user = _make_user()
        target = _make_target()
        stale = _make_stale_job()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([stale]),    # job lookup
            FakeScalarResult([target]),   # ownership check
        ])

        result = _run(get_job_status(job_id=10, user=user, db=db))
        assert result["job"].status == "failed"
        assert result["job"].error_message == "Job timed out"
