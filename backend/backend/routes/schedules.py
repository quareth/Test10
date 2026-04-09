"""Schedule CRUD routes for targets."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models import Schedule, Target, User
from backend.scheduler import (
    add_or_update_schedule,
    get_next_run_time,
    pause_schedule,
    remove_schedule,
    resume_schedule,
)
from backend.schemas import ScheduleCreate, ScheduleOut, ScheduleToggle

router = APIRouter(prefix="/api/targets", tags=["schedules"])


async def _get_user_target(
    target_id: int, user: User, db: AsyncSession
) -> Target:
    """Look up a target belonging to the user, or raise 404."""
    result = await db.execute(
        select(Target).where(Target.id == target_id, Target.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


def _schedule_out(schedule: Schedule) -> ScheduleOut:
    """Build a ScheduleOut from a Schedule model instance."""
    return ScheduleOut(
        id=schedule.id,
        target_id=schedule.target_id,
        interval_type=schedule.interval_type,
        cron_expression=schedule.cron_expression,
        status=schedule.status,
        next_run_at=schedule.next_run_at,
        last_run_at=schedule.last_run_at,
        last_run_status=schedule.last_run_status,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.post("/{target_id}/schedule")
async def create_schedule(
    target_id: int,
    body: ScheduleCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create or update a schedule for the given target."""
    target = await _get_user_target(target_id, user, db)

    # Check for existing schedule
    result = await db.execute(
        select(Schedule).where(Schedule.target_id == target.id)
    )
    schedule = result.scalar_one_or_none()

    if schedule is None:
        schedule = Schedule(
            target_id=target.id,
            interval_type=body.interval_type,
            cron_expression=body.cron_expression,
            status="active",
        )
        db.add(schedule)
    else:
        schedule.interval_type = body.interval_type
        schedule.cron_expression = body.cron_expression
        schedule.status = "active"
        schedule.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(schedule)

    # Register with the scheduler
    try:
        add_or_update_schedule(target.id, schedule)
        next_run = get_next_run_time(target.id)
        if next_run is not None:
            schedule.next_run_at = next_run
            await db.commit()
            await db.refresh(schedule)
    except RuntimeError:
        # Scheduler not initialized (e.g. during testing) -- skip
        pass

    return {"schedule": _schedule_out(schedule)}


@router.get("/{target_id}/schedule")
async def get_schedule(
    target_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the schedule for the given target, or null if none exists."""
    await _get_user_target(target_id, user, db)

    result = await db.execute(
        select(Schedule).where(Schedule.target_id == target_id)
    )
    schedule = result.scalar_one_or_none()

    if schedule is None:
        return {"schedule": None}

    return {"schedule": _schedule_out(schedule)}


@router.delete("/{target_id}/schedule")
async def delete_schedule(
    target_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete the schedule for the given target."""
    await _get_user_target(target_id, user, db)

    result = await db.execute(
        select(Schedule).where(Schedule.target_id == target_id)
    )
    schedule = result.scalar_one_or_none()

    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.delete(schedule)
    await db.commit()

    # Remove from scheduler
    try:
        remove_schedule(target_id)
    except RuntimeError:
        pass

    return {"ok": True}


@router.patch("/{target_id}/schedule")
async def toggle_schedule(
    target_id: int,
    body: ScheduleToggle,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update the status of a schedule (active/paused)."""
    await _get_user_target(target_id, user, db)

    result = await db.execute(
        select(Schedule).where(Schedule.target_id == target_id)
    )
    schedule = result.scalar_one_or_none()

    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.status = body.status
    schedule.updated_at = datetime.now(timezone.utc)

    # Update scheduler
    try:
        if body.status == "paused":
            pause_schedule(target_id)
        else:
            resume_schedule(target_id)
            next_run = get_next_run_time(target_id)
            if next_run is not None:
                schedule.next_run_at = next_run
    except RuntimeError:
        pass

    await db.commit()
    await db.refresh(schedule)

    return {"schedule": _schedule_out(schedule)}
