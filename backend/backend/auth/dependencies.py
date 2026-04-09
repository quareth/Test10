from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.sessions import get_session_user_id
from backend.database import get_db
from backend.models import User


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the session cookie, then return the authenticated User.

    Raises HTTPException(401) when:
    - The ``session_id`` cookie is missing
    - The session token is invalid or expired
    - The user referenced by the session no longer exists
    """
    session_id: str | None = request.cookies.get("session_id")
    if session_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = await get_session_user_id(session_id, db)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return user
