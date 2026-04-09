"""Tests for backend.scraping.scheduled – the schedule executor."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_target(id_: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=id_, url="https://example.com", name="Example")


def _make_schedule(target_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        target_id=target_id,
        last_run_at=None,
        last_run_status=None,
    )


def _make_session(
    target=None,
    existing_job=None,
    schedule=None,
):
    """Build a mock AsyncSession that returns controlled query results."""
    db = AsyncMock()

    # db.get(Target, target_id) -> target or None
    db.get = AsyncMock(return_value=target)

    # Track added objects so we can inspect them
    added_objects: list = []

    def _add(obj):
        added_objects.append(obj)

    db.add = MagicMock(side_effect=_add)
    db.added_objects = added_objects

    # db.commit / db.refresh
    db.commit = AsyncMock()

    async def _refresh(obj):
        # Simulate job getting an id after insert
        if hasattr(obj, "id") and obj.id is None:
            obj.id = 42

    db.refresh = AsyncMock(side_effect=_refresh)

    # Build chained execute -> scalars -> first results
    # We need two different query results:
    #   1st execute: existing running/pending job check
    #   2nd execute: schedule lookup (after job creation)
    #   3rd execute: schedule lookup (after orchestrator)
    call_count = {"n": 0}

    async def _execute(stmt):
        call_count["n"] += 1
        result = MagicMock()
        scalars_mock = MagicMock()

        if call_count["n"] == 1:
            # First query: existing job check
            scalars_mock.first.return_value = existing_job
        else:
            # Subsequent queries: schedule lookup
            scalars_mock.first.return_value = schedule

        result.scalars.return_value = scalars_mock
        return result

    db.execute = AsyncMock(side_effect=_execute)

    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creates_job_and_calls_orchestrator():
    """Executor creates a ScrapeJob with trigger='scheduled' and calls run_scrape."""
    target = _make_target()
    schedule = _make_schedule()
    db = _make_session(target=target, existing_job=None, schedule=schedule)

    mock_run_scrape = AsyncMock()

    with (
        patch(
            "backend.scraping.scheduled.async_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ),
        patch(
            "backend.scraping.scheduled.run_scrape", mock_run_scrape
        ),
    ):
        from backend.scraping.scheduled import run_scheduled_scrape

        await run_scheduled_scrape(target_id=1)

    # Verify a ScrapeJob was added
    assert len(db.added_objects) == 1
    job = db.added_objects[0]
    assert job.trigger == "scheduled"
    assert job.status == "pending"
    assert job.target_id == 1

    # Verify orchestrator was called
    mock_run_scrape.assert_awaited_once()
    call_args = mock_run_scrape.call_args
    assert call_args[0][0] is target  # first arg: target
    assert call_args[0][1] is job  # second arg: job
    assert call_args[0][2] is db  # third arg: db


@pytest.mark.asyncio
async def test_updates_schedule_after_completion():
    """After orchestrator completes, schedule record is updated."""
    target = _make_target()
    schedule = _make_schedule()
    db = _make_session(target=target, existing_job=None, schedule=schedule)

    async def _mock_run_scrape(t, j, d):
        j.status = "complete"

    with (
        patch(
            "backend.scraping.scheduled.async_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ),
        patch(
            "backend.scraping.scheduled.run_scrape",
            AsyncMock(side_effect=_mock_run_scrape),
        ),
    ):
        from backend.scraping.scheduled import run_scheduled_scrape

        await run_scheduled_scrape(target_id=1)

    assert schedule.last_run_status == "complete"
    assert schedule.last_run_at is not None


@pytest.mark.asyncio
async def test_skips_when_job_already_running():
    """Executor skips if a running/pending job already exists for the target."""
    target = _make_target()
    schedule = _make_schedule()
    existing_job = SimpleNamespace(id=99, status="running")
    db = _make_session(
        target=target, existing_job=existing_job, schedule=schedule
    )

    mock_run_scrape = AsyncMock()

    with (
        patch(
            "backend.scraping.scheduled.async_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ),
        patch(
            "backend.scraping.scheduled.run_scrape", mock_run_scrape
        ),
    ):
        from backend.scraping.scheduled import run_scheduled_scrape

        await run_scheduled_scrape(target_id=1)

    # Orchestrator should NOT have been called
    mock_run_scrape.assert_not_awaited()
    # Schedule should be marked as skipped
    assert schedule.last_run_status == "skipped"


@pytest.mark.asyncio
async def test_nonexistent_target_does_not_crash():
    """Executor returns gracefully when target does not exist."""
    db = _make_session(target=None, existing_job=None, schedule=None)

    mock_run_scrape = AsyncMock()

    with (
        patch(
            "backend.scraping.scheduled.async_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ),
        patch(
            "backend.scraping.scheduled.run_scrape", mock_run_scrape
        ),
    ):
        from backend.scraping.scheduled import run_scheduled_scrape

        # Should not raise
        await run_scheduled_scrape(target_id=9999)

    mock_run_scrape.assert_not_awaited()


@pytest.mark.asyncio
async def test_exception_sets_schedule_failed():
    """If run_scrape raises, schedule.last_run_status becomes 'failed'."""
    target = _make_target()
    schedule = _make_schedule()
    db = _make_session(target=target, existing_job=None, schedule=schedule)

    with (
        patch(
            "backend.scraping.scheduled.async_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ),
        patch(
            "backend.scraping.scheduled.run_scrape",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
    ):
        from backend.scraping.scheduled import run_scheduled_scrape

        # Should not raise
        await run_scheduled_scrape(target_id=1)

    assert schedule.last_run_status == "failed"
