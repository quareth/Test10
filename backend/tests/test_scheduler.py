"""Tests for backend.scheduler – APScheduler integration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.scheduler import (
    _build_trigger,
    _job_id,
    add_or_update_schedule,
    get_next_run_time,
    init_scheduler,
    pause_schedule,
    remove_schedule,
    resume_schedule,
    shutdown_scheduler,
)


# ---------------------------------------------------------------------------
# _build_trigger tests
# ---------------------------------------------------------------------------


class TestBuildTrigger:
    def test_6h(self):
        trigger = _build_trigger("6h")
        assert isinstance(trigger, IntervalTrigger)

    def test_12h(self):
        trigger = _build_trigger("12h")
        assert isinstance(trigger, IntervalTrigger)

    def test_daily(self):
        trigger = _build_trigger("daily")
        assert isinstance(trigger, CronTrigger)

    def test_weekly(self):
        trigger = _build_trigger("weekly")
        assert isinstance(trigger, CronTrigger)

    def test_cron_valid(self):
        trigger = _build_trigger("cron", "*/5 * * * *")
        assert isinstance(trigger, CronTrigger)

    def test_cron_missing_expression(self):
        with pytest.raises(ValueError, match="cron_expression is required"):
            _build_trigger("cron")

    def test_unknown_interval(self):
        with pytest.raises(ValueError, match="Unknown interval_type"):
            _build_trigger("every-minute")


# ---------------------------------------------------------------------------
# _job_id tests
# ---------------------------------------------------------------------------


def test_job_id():
    assert _job_id(42) == "scrape-target-42"
    assert _job_id(1) == "scrape-target-1"


# ---------------------------------------------------------------------------
# init_scheduler tests
# ---------------------------------------------------------------------------


def _make_schedule_record(
    target_id: int = 1,
    interval_type: str = "daily",
    cron_expression: str | None = None,
    status: str = "active",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        target_id=target_id,
        interval_type=interval_type,
        cron_expression=cron_expression,
        status=status,
    )


@pytest.mark.asyncio
async def test_init_scheduler_starts_and_registers_jobs():
    """init_scheduler loads active schedules and registers APScheduler jobs."""
    sched1 = _make_schedule_record(target_id=1, interval_type="daily")
    sched2 = _make_schedule_record(target_id=2, interval_type="6h")

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [sched1, sched2]
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_session_ctx = AsyncMock(
        __aenter__=AsyncMock(return_value=mock_db),
        __aexit__=AsyncMock(return_value=False),
    )

    import backend.scheduler as sched_module

    with patch.object(sched_module, "async_session", return_value=mock_session_ctx):
        await init_scheduler()

    # Scheduler should be running
    assert sched_module.scheduler is not None
    assert sched_module.scheduler.running

    jobs = sched_module.scheduler.get_jobs()
    job_ids = {j.id for j in jobs}
    assert "scrape-target-1" in job_ids
    assert "scrape-target-2" in job_ids
    assert len(jobs) == 2

    # Cleanup
    await shutdown_scheduler()
    assert sched_module.scheduler is None


@pytest.mark.asyncio
async def test_init_scheduler_no_active_schedules():
    """init_scheduler starts even when there are no active schedules."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_session_ctx = AsyncMock(
        __aenter__=AsyncMock(return_value=mock_db),
        __aexit__=AsyncMock(return_value=False),
    )

    import backend.scheduler as sched_module

    with patch.object(sched_module, "async_session", return_value=mock_session_ctx):
        await init_scheduler()

    assert sched_module.scheduler is not None
    assert sched_module.scheduler.running
    assert len(sched_module.scheduler.get_jobs()) == 0

    await shutdown_scheduler()


# ---------------------------------------------------------------------------
# add_or_update_schedule tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_or_update_schedule_adds_job():
    """add_or_update_schedule registers a new job in the scheduler."""
    # Start a fresh scheduler with no DB schedules
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_session_ctx = AsyncMock(
        __aenter__=AsyncMock(return_value=mock_db),
        __aexit__=AsyncMock(return_value=False),
    )

    import backend.scheduler as sched_module

    with patch.object(sched_module, "async_session", return_value=mock_session_ctx):
        await init_scheduler()

    # Add a schedule
    schedule = _make_schedule_record(target_id=5, interval_type="12h")
    add_or_update_schedule(5, schedule)

    job = sched_module.scheduler.get_job("scrape-target-5")
    assert job is not None
    assert isinstance(job.trigger, IntervalTrigger)

    # Replace it
    schedule2 = _make_schedule_record(target_id=5, interval_type="weekly")
    add_or_update_schedule(5, schedule2)

    job = sched_module.scheduler.get_job("scrape-target-5")
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)

    await shutdown_scheduler()


# ---------------------------------------------------------------------------
# remove_schedule tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_schedule():
    """remove_schedule removes the APScheduler job."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_session_ctx = AsyncMock(
        __aenter__=AsyncMock(return_value=mock_db),
        __aexit__=AsyncMock(return_value=False),
    )

    import backend.scheduler as sched_module

    with patch.object(sched_module, "async_session", return_value=mock_session_ctx):
        await init_scheduler()

    # Add then remove
    schedule = _make_schedule_record(target_id=3, interval_type="daily")
    add_or_update_schedule(3, schedule)
    assert sched_module.scheduler.get_job("scrape-target-3") is not None

    remove_schedule(3)
    assert sched_module.scheduler.get_job("scrape-target-3") is None

    await shutdown_scheduler()


# ---------------------------------------------------------------------------
# pause / resume tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_and_resume_schedule():
    """pause_schedule pauses a job and resume_schedule resumes it."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_session_ctx = AsyncMock(
        __aenter__=AsyncMock(return_value=mock_db),
        __aexit__=AsyncMock(return_value=False),
    )

    import backend.scheduler as sched_module

    with patch.object(sched_module, "async_session", return_value=mock_session_ctx):
        await init_scheduler()

    schedule = _make_schedule_record(target_id=7, interval_type="6h")
    add_or_update_schedule(7, schedule)

    # Pause
    pause_schedule(7)
    job = sched_module.scheduler.get_job("scrape-target-7")
    assert job is not None
    assert job.next_run_time is None  # paused jobs have no next_run_time

    # Resume
    resume_schedule(7)
    job = sched_module.scheduler.get_job("scrape-target-7")
    assert job is not None
    assert job.next_run_time is not None

    await shutdown_scheduler()


# ---------------------------------------------------------------------------
# get_next_run_time tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_next_run_time():
    """get_next_run_time returns the next run time or None."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_session_ctx = AsyncMock(
        __aenter__=AsyncMock(return_value=mock_db),
        __aexit__=AsyncMock(return_value=False),
    )

    import backend.scheduler as sched_module

    with patch.object(sched_module, "async_session", return_value=mock_session_ctx):
        await init_scheduler()

    # No job yet
    assert get_next_run_time(99) is None

    # Add a job
    schedule = _make_schedule_record(target_id=99, interval_type="daily")
    add_or_update_schedule(99, schedule)

    nrt = get_next_run_time(99)
    assert nrt is not None

    await shutdown_scheduler()


def test_get_next_run_time_no_scheduler():
    """get_next_run_time returns None when scheduler is not initialized."""
    import backend.scheduler as sched_module

    sched_module.scheduler = None
    assert get_next_run_time(1) is None
