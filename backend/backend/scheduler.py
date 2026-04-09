"""APScheduler integration for managing scheduled scrape jobs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from backend.database import async_session
from backend.models import Schedule
from backend.scraping.scheduled import run_scheduled_scrape

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None


def _build_trigger(
    interval_type: str, cron_expression: str | None = None
) -> IntervalTrigger | CronTrigger:
    """Map an interval_type string to an APScheduler trigger."""
    if interval_type == "6h":
        return IntervalTrigger(hours=6)
    elif interval_type == "12h":
        return IntervalTrigger(hours=12)
    elif interval_type == "daily":
        return CronTrigger(hour=0, minute=0)
    elif interval_type == "weekly":
        return CronTrigger(day_of_week="mon", hour=0, minute=0)
    elif interval_type == "cron":
        if not cron_expression:
            raise ValueError("cron_expression is required when interval_type is 'cron'")
        return CronTrigger.from_crontab(cron_expression)
    else:
        raise ValueError(f"Unknown interval_type: {interval_type}")


def _job_id(target_id: int) -> str:
    """Return the APScheduler job id for a given target."""
    return f"scrape-target-{target_id}"


async def init_scheduler() -> None:
    """Create the AsyncIOScheduler, load active schedules from DB, and start."""
    global scheduler

    scheduler = AsyncIOScheduler(
        job_defaults={"coalesce": True, "max_instances": 1}
    )

    # Load active schedules from the database
    async with async_session() as db:
        stmt = select(Schedule).where(Schedule.status == "active")
        result = await db.execute(stmt)
        active_schedules = result.scalars().all()

        for sched in active_schedules:
            try:
                trigger = _build_trigger(sched.interval_type, sched.cron_expression)
                scheduler.add_job(
                    run_scheduled_scrape,
                    trigger=trigger,
                    args=[sched.target_id],
                    id=_job_id(sched.target_id),
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                )
                logger.info(
                    "Registered scheduled job for target %s (%s)",
                    sched.target_id,
                    sched.interval_type,
                )
            except Exception:
                logger.exception(
                    "Failed to register job for target %s", sched.target_id
                )

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))


async def shutdown_scheduler() -> None:
    """Shut down the scheduler without waiting for running jobs."""
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
        scheduler = None


def add_or_update_schedule(target_id: int, schedule: Schedule) -> None:
    """Add or replace an APScheduler job for the given target/schedule."""
    if scheduler is None:
        raise RuntimeError("Scheduler is not initialized")

    trigger = _build_trigger(schedule.interval_type, schedule.cron_expression)
    scheduler.add_job(
        run_scheduled_scrape,
        trigger=trigger,
        args=[target_id],
        id=_job_id(target_id),
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info(
        "Added/updated scheduled job for target %s (%s)",
        target_id,
        schedule.interval_type,
    )


def remove_schedule(target_id: int) -> None:
    """Remove the APScheduler job for the given target."""
    if scheduler is None:
        raise RuntimeError("Scheduler is not initialized")

    job_id = _job_id(target_id)
    try:
        scheduler.remove_job(job_id)
        logger.info("Removed scheduled job %s", job_id)
    except Exception:
        logger.warning("Job %s not found in scheduler", job_id)


def pause_schedule(target_id: int) -> None:
    """Pause the APScheduler job for the given target."""
    if scheduler is None:
        raise RuntimeError("Scheduler is not initialized")

    job_id = _job_id(target_id)
    scheduler.pause_job(job_id)
    logger.info("Paused scheduled job %s", job_id)


def resume_schedule(target_id: int) -> None:
    """Resume the APScheduler job for the given target."""
    if scheduler is None:
        raise RuntimeError("Scheduler is not initialized")

    job_id = _job_id(target_id)
    scheduler.resume_job(job_id)
    logger.info("Resumed scheduled job %s", job_id)


def get_next_run_time(target_id: int) -> Optional[datetime]:
    """Return the next run time for the given target's job, or None."""
    if scheduler is None:
        return None

    job = scheduler.get_job(_job_id(target_id))
    if job is None:
        return None
    return job.next_run_time
