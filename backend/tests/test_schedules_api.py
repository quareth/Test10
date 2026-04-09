"""Tests for backend.routes.schedules -- schedule CRUD API endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.schemas import ScheduleCreate, ScheduleToggle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_user(id_: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=id_, username="testuser")


def _make_target(
    id_: int = 1, user_id: int = 1, url: str = "https://example.com", name: str = "Example"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_, user_id=user_id, url=url, name=name,
        created_at=datetime.now(timezone.utc),
    )


def _make_schedule(
    id_: int = 1,
    target_id: int = 1,
    interval_type: str = "daily",
    cron_expression: str | None = None,
    status: str = "active",
) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=id_,
        target_id=target_id,
        interval_type=interval_type,
        cron_expression=cron_expression,
        status=status,
        next_run_at=None,
        last_run_at=None,
        last_run_status=None,
        created_at=now,
        updated_at=now,
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


def _make_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# POST /api/targets/{target_id}/schedule -- create_schedule
# ---------------------------------------------------------------------------


class TestCreateSchedule:
    def test_creates_new_schedule(self):
        from backend.routes.schedules import create_schedule

        user = _make_user()
        target = _make_target()
        db = _make_db()

        # First execute: target lookup, Second: existing schedule lookup
        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),   # target lookup
            FakeScalarResult([]),         # no existing schedule
        ])

        schedule_obj = _make_schedule(target_id=target.id)

        async def fake_refresh(obj):
            # Simulate what refresh does for a new schedule
            obj.id = schedule_obj.id
            obj.target_id = schedule_obj.target_id
            obj.interval_type = "daily"
            obj.cron_expression = None
            obj.status = "active"
            obj.next_run_at = None
            obj.last_run_at = None
            obj.last_run_status = None
            obj.created_at = schedule_obj.created_at
            obj.updated_at = schedule_obj.updated_at

        db.refresh = fake_refresh

        body = ScheduleCreate(interval_type="daily")

        with patch("backend.routes.schedules.add_or_update_schedule"), \
             patch("backend.routes.schedules.get_next_run_time", return_value=None):
            result = _run(create_schedule(target_id=1, body=body, user=user, db=db))

        assert "schedule" in result
        assert result["schedule"].interval_type == "daily"
        assert result["schedule"].status == "active"
        db.add.assert_called_once()

    def test_updates_existing_schedule(self):
        from backend.routes.schedules import create_schedule

        user = _make_user()
        target = _make_target()
        existing = _make_schedule(target_id=target.id, interval_type="6h")
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),     # target lookup
            FakeScalarResult([existing]),   # existing schedule found
        ])

        async def fake_refresh(obj):
            pass  # existing schedule is mutated in place

        db.refresh = fake_refresh

        body = ScheduleCreate(interval_type="daily")

        with patch("backend.routes.schedules.add_or_update_schedule"), \
             patch("backend.routes.schedules.get_next_run_time", return_value=None):
            result = _run(create_schedule(target_id=1, body=body, user=user, db=db))

        assert "schedule" in result
        # The existing schedule should have been updated
        assert existing.interval_type == "daily"
        assert existing.status == "active"
        # add should NOT have been called since we updated the existing
        db.add.assert_not_called()

    def test_returns_404_for_missing_target(self):
        from backend.routes.schedules import create_schedule

        user = _make_user()
        db = _make_db()
        db.execute = AsyncMock(return_value=FakeScalarResult([]))

        body = ScheduleCreate(interval_type="daily")

        with pytest.raises(HTTPException) as exc_info:
            _run(create_schedule(target_id=999, body=body, user=user, db=db))
        assert exc_info.value.status_code == 404

    def test_validates_invalid_interval_type(self):
        """Schema rejects invalid interval_type before the route runs."""
        with pytest.raises(Exception):
            ScheduleCreate(interval_type="invalid")

    def test_validates_cron_without_expression(self):
        """Schema rejects cron interval_type without cron_expression."""
        with pytest.raises(Exception):
            ScheduleCreate(interval_type="cron")

    def test_accepts_cron_with_expression(self):
        body = ScheduleCreate(interval_type="cron", cron_expression="0 6 * * *")
        assert body.interval_type == "cron"
        assert body.cron_expression == "0 6 * * *"

    def test_creates_schedule_with_cron(self):
        from backend.routes.schedules import create_schedule

        user = _make_user()
        target = _make_target()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),
            FakeScalarResult([]),
        ])

        schedule_obj = _make_schedule(
            target_id=target.id,
            interval_type="cron",
            cron_expression="*/30 * * * *",
        )

        async def fake_refresh(obj):
            obj.id = schedule_obj.id
            obj.target_id = schedule_obj.target_id
            obj.interval_type = "cron"
            obj.cron_expression = "*/30 * * * *"
            obj.status = "active"
            obj.next_run_at = None
            obj.last_run_at = None
            obj.last_run_status = None
            obj.created_at = schedule_obj.created_at
            obj.updated_at = schedule_obj.updated_at

        db.refresh = fake_refresh

        body = ScheduleCreate(interval_type="cron", cron_expression="*/30 * * * *")

        with patch("backend.routes.schedules.add_or_update_schedule"), \
             patch("backend.routes.schedules.get_next_run_time", return_value=None):
            result = _run(create_schedule(target_id=1, body=body, user=user, db=db))

        assert result["schedule"].interval_type == "cron"
        assert result["schedule"].cron_expression == "*/30 * * * *"


# ---------------------------------------------------------------------------
# GET /api/targets/{target_id}/schedule -- get_schedule
# ---------------------------------------------------------------------------


class TestGetSchedule:
    def test_returns_existing_schedule(self):
        from backend.routes.schedules import get_schedule

        user = _make_user()
        target = _make_target()
        schedule = _make_schedule(target_id=target.id)
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),     # target lookup
            FakeScalarResult([schedule]),   # schedule lookup
        ])

        result = _run(get_schedule(target_id=1, user=user, db=db))
        assert "schedule" in result
        assert result["schedule"].id == schedule.id
        assert result["schedule"].interval_type == "daily"

    def test_returns_null_when_no_schedule(self):
        from backend.routes.schedules import get_schedule

        user = _make_user()
        target = _make_target()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),  # target lookup
            FakeScalarResult([]),        # no schedule
        ])

        result = _run(get_schedule(target_id=1, user=user, db=db))
        assert result["schedule"] is None

    def test_returns_404_for_missing_target(self):
        from backend.routes.schedules import get_schedule

        user = _make_user()
        db = _make_db()
        db.execute = AsyncMock(return_value=FakeScalarResult([]))

        with pytest.raises(HTTPException) as exc_info:
            _run(get_schedule(target_id=999, user=user, db=db))
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/targets/{target_id}/schedule -- delete_schedule
# ---------------------------------------------------------------------------


class TestDeleteSchedule:
    def test_deletes_existing_schedule(self):
        from backend.routes.schedules import delete_schedule

        user = _make_user()
        target = _make_target()
        schedule = _make_schedule(target_id=target.id)
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),     # target lookup
            FakeScalarResult([schedule]),   # schedule lookup
        ])

        with patch("backend.routes.schedules.remove_schedule") as mock_remove:
            result = _run(delete_schedule(target_id=1, user=user, db=db))
            mock_remove.assert_called_once_with(1)

        assert result == {"ok": True}
        db.delete.assert_called_once_with(schedule)

    def test_returns_404_for_no_schedule(self):
        from backend.routes.schedules import delete_schedule

        user = _make_user()
        target = _make_target()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),  # target lookup
            FakeScalarResult([]),        # no schedule
        ])

        with pytest.raises(HTTPException) as exc_info:
            _run(delete_schedule(target_id=1, user=user, db=db))
        assert exc_info.value.status_code == 404

    def test_returns_404_for_missing_target(self):
        from backend.routes.schedules import delete_schedule

        user = _make_user()
        db = _make_db()
        db.execute = AsyncMock(return_value=FakeScalarResult([]))

        with pytest.raises(HTTPException) as exc_info:
            _run(delete_schedule(target_id=999, user=user, db=db))
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/targets/{target_id}/schedule -- toggle_schedule
# ---------------------------------------------------------------------------


class TestToggleSchedule:
    def test_pauses_schedule(self):
        from backend.routes.schedules import toggle_schedule

        user = _make_user()
        target = _make_target()
        schedule = _make_schedule(target_id=target.id, status="active")
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),     # target lookup
            FakeScalarResult([schedule]),   # schedule lookup
        ])

        async def fake_refresh(obj):
            pass

        db.refresh = fake_refresh

        body = ScheduleToggle(status="paused")

        with patch("backend.routes.schedules.pause_schedule") as mock_pause:
            result = _run(toggle_schedule(target_id=1, body=body, user=user, db=db))
            mock_pause.assert_called_once_with(1)

        assert result["schedule"].status == "paused"

    def test_resumes_schedule(self):
        from backend.routes.schedules import toggle_schedule

        user = _make_user()
        target = _make_target()
        schedule = _make_schedule(target_id=target.id, status="paused")
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),     # target lookup
            FakeScalarResult([schedule]),   # schedule lookup
        ])

        async def fake_refresh(obj):
            pass

        db.refresh = fake_refresh

        body = ScheduleToggle(status="active")

        with patch("backend.routes.schedules.resume_schedule") as mock_resume, \
             patch("backend.routes.schedules.get_next_run_time", return_value=None):
            result = _run(toggle_schedule(target_id=1, body=body, user=user, db=db))
            mock_resume.assert_called_once_with(1)

        assert result["schedule"].status == "active"

    def test_returns_404_for_no_schedule(self):
        from backend.routes.schedules import toggle_schedule

        user = _make_user()
        target = _make_target()
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),  # target lookup
            FakeScalarResult([]),        # no schedule
        ])

        body = ScheduleToggle(status="paused")

        with pytest.raises(HTTPException) as exc_info:
            _run(toggle_schedule(target_id=1, body=body, user=user, db=db))
        assert exc_info.value.status_code == 404

    def test_returns_404_for_missing_target(self):
        from backend.routes.schedules import toggle_schedule

        user = _make_user()
        db = _make_db()
        db.execute = AsyncMock(return_value=FakeScalarResult([]))

        body = ScheduleToggle(status="paused")

        with pytest.raises(HTTPException) as exc_info:
            _run(toggle_schedule(target_id=999, body=body, user=user, db=db))
        assert exc_info.value.status_code == 404

    def test_validates_invalid_status(self):
        """Schema rejects status values other than active/paused."""
        with pytest.raises(Exception):
            ScheduleToggle(status="invalid")


# ---------------------------------------------------------------------------
# list_targets with schedule info
# ---------------------------------------------------------------------------


class TestListTargetsWithScheduleInfo:
    def test_includes_schedule_info(self):
        from backend.routes.targets import list_targets

        user = _make_user()
        target = _make_target()
        job = SimpleNamespace(
            id=10, target_id=1, status="complete",
            pages_found=5, pages_scraped=5,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            error_message=None,
        )
        schedule = _make_schedule(target_id=target.id, status="active")
        schedule.next_run_at = datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),    # targets query
            FakeScalarResult([job]),       # latest job
            FakeScalarResult([schedule]),  # schedule
        ])

        result = _run(list_targets(user=user, db=db))
        t = result["targets"][0]
        assert t.has_schedule is True
        assert t.schedule_status == "active"
        assert t.next_run_at == datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)

    def test_no_schedule_returns_defaults(self):
        from backend.routes.targets import list_targets

        user = _make_user()
        target = _make_target()
        job = SimpleNamespace(
            id=10, target_id=1, status="complete",
            pages_found=5, pages_scraped=5,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            error_message=None,
        )
        db = _make_db()

        db.execute = AsyncMock(side_effect=[
            FakeScalarResult([target]),  # targets query
            FakeScalarResult([job]),     # latest job
            FakeScalarResult([]),        # no schedule
        ])

        result = _run(list_targets(user=user, db=db))
        t = result["targets"][0]
        assert t.has_schedule is False
        assert t.schedule_status is None
        assert t.next_run_at is None
