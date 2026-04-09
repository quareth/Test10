"""Database-backed session management with HMAC-signed session tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import Session


def _sign_session_id(raw_id: str) -> str:
    """Return ``raw_id.signature`` where signature is an HMAC-SHA256 hex digest."""
    sig = hmac.new(
        settings.SECRET_KEY.encode(), raw_id.encode(), hashlib.sha256
    ).hexdigest()
    return f"{raw_id}.{sig}"


def _verify_and_split(signed_id: str) -> str | None:
    """Verify the HMAC signature and return the raw session ID, or None."""
    if "." not in signed_id:
        return None
    raw_id, sig = signed_id.rsplit(".", 1)
    expected = hmac.new(
        settings.SECRET_KEY.encode(), raw_id.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    return raw_id


async def create_session(user_id: int, db: AsyncSession) -> str:
    """Create a DB-backed session. Returns a signed session token."""
    raw_id = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.SESSION_EXPIRY_HOURS
    )
    session = Session(
        session_id=raw_id,
        user_id=user_id,
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    return _sign_session_id(raw_id)


async def get_session_user_id(signed_id: str, db: AsyncSession) -> int | None:
    """Verify HMAC, look up session in DB, check expiry. Return user_id or None."""
    raw_id = _verify_and_split(signed_id)
    if raw_id is None:
        return None

    result = await db.execute(
        select(Session).where(Session.session_id == raw_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        # Expired -- clean it up
        await db.delete(session)
        await db.commit()
        return None

    return session.user_id


async def delete_session(signed_id: str, db: AsyncSession) -> None:
    """Delete a session row from the database."""
    raw_id = _verify_and_split(signed_id)
    if raw_id is None:
        return

    result = await db.execute(
        select(Session).where(Session.session_id == raw_id)
    )
    session = result.scalar_one_or_none()
    if session is not None:
        await db.delete(session)
        await db.commit()


async def cleanup_expired_sessions(db: AsyncSession) -> None:
    """Delete all expired session rows."""
    await db.execute(
        delete(Session).where(Session.expires_at < datetime.now(timezone.utc))
    )
    await db.commit()
