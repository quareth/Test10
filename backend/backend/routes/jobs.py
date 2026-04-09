"""Job status, snapshot metadata, and download routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models import ScrapeJob, Snapshot, Target, User
from backend.schemas import ScrapeJobOut, SnapshotOut
from backend.storage import generate_zip, list_snapshot_files, read_file

router = APIRouter(tags=["jobs"])

_STALE_JOB_CUTOFF = timedelta(hours=1)


def _as_utc(value: datetime) -> datetime:
    """Normalize DB datetimes so stale-job comparisons are safe."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _correct_stale_jobs(
    jobs: list[ScrapeJob], db: AsyncSession
) -> bool:
    """Mark running jobs older than 1 hour as failed.

    Returns True if any jobs were corrected.
    """
    stale_cutoff = datetime.now(timezone.utc) - _STALE_JOB_CUTOFF
    corrected = False
    for job in jobs:
        if job.status == "running" and _as_utc(job.started_at) < stale_cutoff:
            job.status = "failed"
            job.error_message = "Job timed out"
            job.completed_at = datetime.now(timezone.utc)
            corrected = True
    if corrected:
        await db.commit()
    return corrected


async def _verify_target_ownership(
    target_id: int, user: User, db: AsyncSession
) -> Target:
    """Load a target and verify it belongs to the authenticated user.

    Raises HTTPException(404) if the target does not exist or is not owned.
    """
    result = await db.execute(
        select(Target).where(Target.id == target_id, Target.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


async def _get_job_with_ownership(
    job_id: int, user: User, db: AsyncSession
) -> ScrapeJob:
    """Load a job and verify the parent target belongs to the authenticated user.

    Raises HTTPException(404) if the job does not exist or the target is not owned.
    """
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify ownership through the target
    await _verify_target_ownership(job.target_id, user, db)
    return job


def _job_out(job: ScrapeJob) -> ScrapeJobOut:
    """Build a ScrapeJobOut from a ScrapeJob model instance."""
    return ScrapeJobOut(
        id=job.id,
        target_id=job.target_id,
        status=job.status,
        trigger=getattr(job, "trigger", None) or "manual",
        pages_found=job.pages_found,
        pages_scraped=job.pages_scraped,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


@router.get("/api/targets/{target_id}/jobs")
async def list_jobs(
    target_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return all scrape jobs for the given target, ordered by started_at desc.

    Verifies target ownership; returns 404 if the target does not exist
    or is not owned by the authenticated user.
    """
    await _verify_target_ownership(target_id, user, db)

    result = await db.execute(
        select(ScrapeJob)
        .where(ScrapeJob.target_id == target_id)
        .order_by(ScrapeJob.started_at.desc())
    )
    jobs = list(result.scalars().all())

    # Correct stale running jobs (>1 hour old) so they appear as failed
    await _correct_stale_jobs(jobs, db)

    return {"jobs": [_job_out(job) for job in jobs]}


@router.get("/api/jobs/{job_id}/status")
async def get_job_status(
    job_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lightweight polling endpoint returning current job status.

    Returns status, pages_found, pages_scraped, and error_message.
    Verifies target ownership through the job's parent target.
    """
    job = await _get_job_with_ownership(job_id, user, db)

    # Correct stale running job (>1 hour old) so it appears as failed
    await _correct_stale_jobs([job], db)

    return {"job": _job_out(job)}


@router.get("/api/jobs/{job_id}/snapshot")
async def get_job_snapshot(
    job_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return snapshot metadata and file list for a completed job.

    Returns 404 if the job has no snapshot or the target is not owned.
    """
    job = await _get_job_with_ownership(job_id, user, db)

    result = await db.execute(
        select(Snapshot).where(Snapshot.job_id == job.id)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    files = list_snapshot_files(snapshot.storage_path)
    snapshot_out = SnapshotOut(
        id=snapshot.id,
        job_id=snapshot.job_id,
        storage_path=snapshot.storage_path,
        file_count=snapshot.file_count,
        total_size_bytes=snapshot.total_size_bytes,
        created_at=snapshot.created_at,
    )
    return {"snapshot": snapshot_out, "files": files}


@router.get("/api/snapshots/{snapshot_id}/download")
async def download_snapshot(
    snapshot_id: int,
    format: str = Query(..., description="Download format: bulk, structured_zip, or file"),
    path: Optional[str] = Query(None, description="File path within snapshot (required when format=file)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download snapshot content in the requested format.

    Formats:
        bulk: serves bulk.md as text/markdown attachment
        structured_zip: serves zip of the structured/ directory
        file: serves an individual file at the given path

    Returns 404 if snapshot not found, not owned, or file missing.
    Returns 400 for invalid format or missing path parameter.
    """
    # Load snapshot
    result = await db.execute(
        select(Snapshot).where(Snapshot.id == snapshot_id)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Verify ownership through job -> target chain
    job_result = await db.execute(
        select(ScrapeJob).where(ScrapeJob.id == snapshot.job_id)
    )
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    await _verify_target_ownership(job.target_id, user, db)

    if format == "bulk":
        try:
            content = read_file(snapshot.storage_path, "bulk.md")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Bulk file not found")
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=bulk.md"},
        )

    if format == "structured_zip":
        try:
            zip_buffer = generate_zip(snapshot.storage_path, "structured")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Structured files not found")
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=structured.zip"},
        )

    if format == "file":
        if not path:
            raise HTTPException(status_code=400, detail="path parameter is required when format=file")
        try:
            content = read_file(snapshot.storage_path, path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="File not found")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file path")
        # Determine filename from the path
        filename = path.rsplit("/", 1)[-1] if "/" in path else path
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    raise HTTPException(status_code=400, detail="Invalid format. Use: bulk, structured_zip, or file")
