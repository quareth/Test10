"""Tests for backend.routes.targets -- target CRUD and scrape trigger."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.schemas import TargetCreate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_user(id_: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=id_, username="testuser")


def _make_target(id_: int = 1, user_id: int = 1, url: str = "https://example.com", name: str = "Example") -> SimpleNamespace:
    return SimpleNamespace(
        id=id_, user_id=user_id, url=url, name=name,
        created_at=datetime.now(timezone.utc),
    )


def _make_job(
    id_: int = 10, target_id: int = 1, status: str = "complete",
    started_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_, target_id=target_id, status=status,
        pages_found=5, pages_scraped=5,
        started_at=started_at or datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        error_message=None,
    )


# ---------------------------------------------------------------------------
# Fake DB helpers
# ---------------------------------------------------------------------------

class FakeScalarResult:
    """Mimics the scalar query result interface."""
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


class FakeRowResult:
    """Mimics the row query result interface (for Snapshot.storage_path selects)."""
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


def _make_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# GET /api/targets -- list_targets
# ---------------------------------------------------------------------------


class TestListTargets:
    def test_returns_user_targets_with_last_job_status(self):
        from backend.routes.targets import list_targets

        user = _make_user()
        target = _make_target()
        job = _make_job()
        db = _make_db()

        # First execute: targets query
        # Second execute: latest job for that target
        # Third execute: schedule for that target
        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),
            FakeScalarResult([job]),
            FakeScalarResult([]),
        ])

        result = _run(list_targets(user=user, db=db))
        assert "targets" in result
        assert len(result["targets"]) == 1
        t = result["targets"][0]
        assert t.id == target.id
        assert t.last_job_status == "complete"

    def test_returns_empty_list_for_no_targets(self):
        from backend.routes.targets import list_targets

        user = _make_user()
        db = _make_db()
        db.execute = AsyncMock(return_value=FakeScalarResult([]))

        result = _run(list_targets(user=user, db=db))
        assert result["targets"] == []


# ---------------------------------------------------------------------------
# POST /api/targets -- create_target
# ---------------------------------------------------------------------------


class TestCreateTarget:
    def test_validates_url_and_returns_201(self):
        from backend.routes.targets import create_target

        user = _make_user()
        db = _make_db()

        created_target = _make_target()

        async def fake_refresh(obj):
            obj.id = created_target.id
            obj.url = created_target.url
            obj.name = created_target.name
            obj.created_at = created_target.created_at

        db.refresh = fake_refresh

        body = TargetCreate(url="https://example.com", name="Example")
        result = _run(create_target(body=body, user=user, db=db))

        assert "target" in result
        assert result["target"].name == "Example"
        db.add.assert_called_once()

    def test_rejects_invalid_url(self):
        """TargetCreate schema should reject non-HTTP URLs."""
        with pytest.raises(Exception):
            TargetCreate(url="not-a-url", name="Bad")


# ---------------------------------------------------------------------------
# DELETE /api/targets/{id} -- delete_target
# ---------------------------------------------------------------------------


class TestDeleteTarget:
    def test_cascades_and_returns_ok(self):
        from backend.routes.targets import delete_target

        user = _make_user()
        target = _make_target()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),       # target lookup
            FakeRowResult([("snap/path",)]),  # snapshot paths
        ])

        with patch("backend.routes.targets.delete_snapshot_files") as mock_del:
            result = _run(delete_target(target_id=1, user=user, db=db))
            mock_del.assert_called_once_with("snap/path")

        assert result == {"ok": True}

    def test_returns_404_for_non_owned(self):
        from backend.routes.targets import delete_target
        from fastapi import HTTPException

        user = _make_user(id_=999)
        db = _make_db()
        db.execute = AsyncMock(return_value=FakeScalarResult([]))

        with pytest.raises(HTTPException) as exc_info:
            _run(delete_target(target_id=1, user=user, db=db))
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/targets/{id}/scrape -- trigger_scrape
# ---------------------------------------------------------------------------


class TestTriggerScrape:
    def test_creates_job_returns_201(self):
        from backend.routes.targets import trigger_scrape

        user = _make_user()
        target = _make_target()
        new_job = _make_job(id_=20, status="pending")
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),   # target lookup
            FakeScalarResult([]),          # active jobs (none)
            FakeScalarResult([]),          # remaining after stale correction
        ])

        async def fake_refresh(obj):
            obj.id = new_job.id
            obj.target_id = target.id
            obj.status = "pending"
            obj.pages_found = 0
            obj.pages_scraped = 0
            obj.started_at = datetime.now(timezone.utc)
            obj.completed_at = None
            obj.error_message = None

        db.refresh = fake_refresh

        bg = MagicMock()
        result = _run(trigger_scrape(target_id=1, background_tasks=bg, user=user, db=db))

        assert "job" in result
        assert result["job"].status == "pending"
        bg.add_task.assert_called_once()

    def test_returns_409_for_active_job(self):
        from backend.routes.targets import trigger_scrape
        from fastapi import HTTPException

        user = _make_user()
        target = _make_target()
        active_job = _make_job(status="running")
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),        # target lookup
            FakeScalarResult([active_job]),     # active jobs
            FakeScalarResult([active_job]),     # remaining after stale check
        ])

        bg = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            _run(trigger_scrape(target_id=1, background_tasks=bg, user=user, db=db))
        assert exc_info.value.status_code == 409
        assert "already running" in exc_info.value.detail

    def test_stale_job_cleanup(self):
        from backend.routes.targets import trigger_scrape

        user = _make_user()
        target = _make_target()
        # A stale running job older than 1 hour
        stale_job = _make_job(
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        new_job = _make_job(id_=30, status="pending")
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),       # target lookup
            FakeScalarResult([stale_job]),     # active jobs (stale)
            FakeScalarResult([]),              # remaining after stale correction (none)
        ])

        async def fake_refresh(obj):
            obj.id = new_job.id
            obj.target_id = target.id
            obj.status = "pending"
            obj.pages_found = 0
            obj.pages_scraped = 0
            obj.started_at = datetime.now(timezone.utc)
            obj.completed_at = None
            obj.error_message = None

        db.refresh = fake_refresh

        bg = MagicMock()
        result = _run(trigger_scrape(target_id=1, background_tasks=bg, user=user, db=db))

        # Stale job should have been marked failed
        assert stale_job.status == "failed"
        assert "job" in result
