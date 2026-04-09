"""Schedule executor: runs a scrape triggered by the scheduler."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from backend.database import async_session
from backend.models import Schedule, ScrapeJob, Target
from backend.scraping.orchestrator import run_scrape

logger = logging.getLogger(__name__)


async def run_scheduled_scrape(target_id: int) -> None:
    """Execute a scheduled scrape for the given target.

    Opens its own database session, creates a ScrapeJob with trigger="scheduled",
    delegates to the existing orchestrator, and updates the Schedule record with
    the outcome.  Never raises -- all exceptions are caught and logged.
    """
    async with async_session() as db:
        try:
            # 1. Look up target
            target = await db.get(Target, target_id)
            if target is None:
                logger.warning(
                    "Scheduled scrape skipped: target %s not found", target_id
                )
                return

            # 2. Check for running/pending jobs
            existing_stmt = select(ScrapeJob).where(
                ScrapeJob.target_id == target_id,
                ScrapeJob.status.in_(["running", "pending"]),
            )
            existing_result = await db.execute(existing_stmt)
            existing_job = existing_result.scalars().first()

            if existing_job is not None:
                logger.info(
                    "Scheduled scrape skipped for target %s: "
                    "job %s already in progress (status=%s)",
                    target_id,
                    existing_job.id,
                    existing_job.status,
                )
                # Update schedule status
                schedule_stmt = select(Schedule).where(
                    Schedule.target_id == target_id
                )
                schedule_result = await db.execute(schedule_stmt)
                schedule = schedule_result.scalars().first()
                if schedule is not None:
                    schedule.last_run_status = "skipped"
                    await db.commit()
                return

            # 3. Create new ScrapeJob
            job = ScrapeJob(
                target_id=target_id,
                trigger="scheduled",
                status="pending",
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            # 4. Run the scrape orchestrator
            await run_scrape(target, job, db)

            # 5. Refresh job to get final status set by orchestrator
            await db.refresh(job)

            # 6. Update schedule record
            schedule_stmt = select(Schedule).where(
                Schedule.target_id == target_id
            )
            schedule_result = await db.execute(schedule_stmt)
            schedule = schedule_result.scalars().first()
            if schedule is not None:
                schedule.last_run_at = datetime.now(timezone.utc)
                schedule.last_run_status = job.status
                await db.commit()

        except Exception:
            logger.exception(
                "Scheduled scrape failed for target %s", target_id
            )
            # Attempt to update schedule status to "failed"
            try:
                schedule_stmt = select(Schedule).where(
                    Schedule.target_id == target_id
                )
                schedule_result = await db.execute(schedule_stmt)
                schedule = schedule_result.scalars().first()
                if schedule is not None:
                    schedule.last_run_status = "failed"
                    await db.commit()
            except Exception:
                logger.exception(
                    "Failed to update schedule status for target %s",
                    target_id,
                )
