"""Target CRUD routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.database import async_session, get_db
from backend.models import Schedule, ScrapeJob, Snapshot, Target, User
from backend.schemas import ScrapeJobOut, TargetCreate, TargetOut
from backend.scraping.orchestrator import run_scrape
from backend.storage import delete_snapshot_files

router = APIRouter(prefix="/api/targets", tags=["targets"])


def _as_utc(value: datetime) -> datetime:
    """Normalize DB datetimes so stale-job comparisons are safe."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _target_out(
    target: Target,
    last_job: ScrapeJob | None,
    schedule: Schedule | None = None,
) -> TargetOut:
    """Build a TargetOut from a Target, its optional latest job, and optional schedule."""
    return TargetOut(
        id=target.id,
        url=target.url,
        name=target.name,
        created_at=target.created_at,
        last_job_status=last_job.status if last_job else None,
        last_scraped_at=last_job.completed_at if last_job else None,
        has_schedule=schedule is not None,
        schedule_status=schedule.status if schedule else None,
        next_run_at=schedule.next_run_at if schedule else None,
    )


@router.get("")
async def list_targets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return all targets for the authenticated user, ordered by created_at desc.

    Each target includes last_job_status and last_scraped_at from the latest
    ScrapeJob (by started_at desc).
    """
    result = await db.execute(
        select(Target)
        .where(Target.user_id == user.id)
        .order_by(Target.created_at.desc())
    )
    targets = result.scalars().all()

    out: list[TargetOut] = []
    for target in targets:
        # Fetch the most recent job for this target
        job_result = await db.execute(
            select(ScrapeJob)
            .where(ScrapeJob.target_id == target.id)
            .order_by(ScrapeJob.started_at.desc())
            .limit(1)
        )
        last_job = job_result.scalar_one_or_none()

        # Fetch the schedule for this target
        sched_result = await db.execute(
            select(Schedule).where(Schedule.target_id == target.id)
        )
        schedule = sched_result.scalar_one_or_none()

        out.append(_target_out(target, last_job, schedule))

    return {"targets": out}


@router.post("", status_code=201)
async def create_target(
    body: TargetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new target for the authenticated user."""
    target = Target(
        user_id=user.id,
        url=str(body.url),
        name=body.name,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)

    return {"target": _target_out(target, None)}


@router.delete("/{target_id}")
async def delete_target(
    target_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a target owned by the authenticated user.

    Cascades deletion to jobs and snapshots in the database.
    Removes snapshot files from disk.
    """
    result = await db.execute(
        select(Target).where(Target.id == target_id, Target.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")

    # Collect snapshot storage paths before cascade deletes them from DB
    snapshot_result = await db.execute(
        select(Snapshot.storage_path)
        .join(ScrapeJob, ScrapeJob.id == Snapshot.job_id)
        .where(ScrapeJob.target_id == target.id)
    )
    storage_paths = [row[0] for row in snapshot_result.all()]

    # Delete target (cascades to jobs and snapshots in DB)
    await db.delete(target)
    await db.commit()

    # Clean up snapshot files from disk
    for path in storage_paths:
        delete_snapshot_files(path)

    return {"ok": True}


async def _run_scrape_with_session(target_id: int, job_id: int) -> None:
    """Run the scrape orchestrator with its own DB session.

    BackgroundTasks outlive the request, so the request-scoped session
    cannot be reused. This wrapper opens a fresh session, reloads the
    ORM objects, and passes them to the orchestrator.
    """
    async with async_session() as db:
        target = await db.get(Target, target_id)
        job = await db.get(ScrapeJob, job_id)
        if target is None or job is None:
            return
        await run_scrape(target, job, db)


@router.post("/{target_id}/scrape", status_code=201)
async def trigger_scrape(
    target_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a scrape for the given target.

    Returns 404 if the target does not exist or is not owned by the user.
    Returns 409 if an active (running/pending) job already exists.
    Stale running jobs older than 1 hour are corrected to failed before
    the conflict check.
    """
    # 1. Verify target exists and belongs to user
    result = await db.execute(
        select(Target).where(Target.id == target_id, Target.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")

    # 2. Query for existing running/pending jobs
    active_result = await db.execute(
        select(ScrapeJob).where(
            ScrapeJob.target_id == target.id,
            ScrapeJob.status.in_(["running", "pending"]),
        )
    )
    active_jobs = active_result.scalars().all()

    # 3. Correct stale running jobs (>1 hour old)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    for job in active_jobs:
        if job.status == "running" and _as_utc(job.started_at) < stale_cutoff:
            job.status = "failed"
            job.error_message = "Job timed out"
            job.completed_at = datetime.now(timezone.utc)
    await db.commit()

    # 4. Check if any active jobs remain after stale correction
    remaining_result = await db.execute(
        select(ScrapeJob).where(
            ScrapeJob.target_id == target.id,
            ScrapeJob.status.in_(["running", "pending"]),
        )
    )
    remaining = remaining_result.scalars().first()
    if remaining is not None:
        raise HTTPException(status_code=409, detail="A scrape is already running for this target")

    # 5. Create new ScrapeJob
    new_job = ScrapeJob(
        target_id=target.id,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)

    # 6. Kick off background scrape with its own session
    background_tasks.add_task(_run_scrape_with_session, target.id, new_job.id)

    # 7. Return 201 with job and null snapshot
    job_out = ScrapeJobOut(
        id=new_job.id,
        target_id=new_job.target_id,
        status=new_job.status,
        trigger=new_job.trigger or "manual",
        pages_found=new_job.pages_found,
        pages_scraped=new_job.pages_scraped,
        started_at=new_job.started_at,
        completed_at=new_job.completed_at,
        error_message=new_job.error_message,
    )
    return {"job": job_out, "snapshot": None}
