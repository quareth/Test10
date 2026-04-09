"""Authentication routes: login, logout, and current-user check."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.passwords import verify_password
from backend.auth.sessions import create_session, delete_session
from backend.database import get_db
from backend.models import User
from backend.schemas import UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate credentials, create session, set HttpOnly cookie, return user."""
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id = await create_session(user.id, db)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        path="/",
    )

    return {"user": UserOut(id=user.id, username=user.username)}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete server-side session and clear the session cookie."""
    session_id: str | None = request.cookies.get("session_id")
    if session_id is not None:
        await delete_session(session_id, db)

    response.delete_cookie(key="session_id", path="/")
    return {"ok": True}


@router.get("/me")
async def me(
    user: User = Depends(get_current_user),
) -> dict:
    """Return the currently authenticated user."""
    return {"user": UserOut(id=user.id, username=user.username)}
