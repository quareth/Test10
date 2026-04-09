"""
Phase 2 E2E tests: Authentication flows.

Tests the full auth lifecycle against the real ASGI app with an isolated
temporary SQLite database. No external server process needed -- httpx
speaks ASGI directly.

Usage:
    cd backend
    DATABASE_URL="sqlite+aiosqlite:///./test_auth_e2e.db" \
        .venv/bin/python tests/e2e/test_auth_e2e.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Isolated DB setup -- must happen before any backend import so the Settings
# singleton picks up the override.
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_TEST_DB_PATH = _BACKEND_DIR / "test_auth_e2e.db"

# Ensure the backend package is importable
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Force a temporary database for isolation
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"

import httpx  # noqa: E402

# We import the app lazily so the env override is already in place.
from backend.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_passed: list[str] = []
_failed: list[tuple[str, str]] = []


def _record(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        _passed.append(name)
        print(f"  PASS  {name}")
    else:
        _failed.append((name, detail))
        print(f"  FAIL  {name}: {detail}")


def _cleanup_db() -> None:
    for suffix in ("", "-shm", "-wal"):
        p = _TEST_DB_PATH.parent / (_TEST_DB_PATH.name + suffix)
        if p.exists():
            p.unlink()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_cli_create_user() -> None:
    """CLI: create-user succeeds; duplicate gives clear error."""
    _cleanup_db()

    python = str(_BACKEND_DIR / ".venv" / "bin" / "python")
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{_TEST_DB_PATH}"}

    # First creation -- should succeed
    result = subprocess.run(
        [python, "-m", "backend.cli", "create-user", "cliuser", "clipass"],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_DIR),
        env=env,
        timeout=30,
    )
    ok = result.returncode == 0 and "created successfully" in result.stdout
    _record(
        "cli_create_user_success",
        ok,
        f"rc={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}",
    )

    # Duplicate -- should fail with clear message
    result2 = subprocess.run(
        [python, "-m", "backend.cli", "create-user", "cliuser", "clipass"],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_DIR),
        env=env,
        timeout=30,
    )
    ok2 = result2.returncode != 0 and "already exists" in result2.stderr
    _record(
        "cli_create_user_duplicate_error",
        ok2,
        f"rc={result2.returncode} stdout={result2.stdout!r} stderr={result2.stderr!r}",
    )


async def test_login_success() -> None:
    """POST /api/auth/login with correct creds returns 200 + user + session cookie."""
    _cleanup_db()

    # Seed a user via CLI
    python = str(_BACKEND_DIR / ".venv" / "bin" / "python")
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{_TEST_DB_PATH}"}
    subprocess.run(
        [python, "-m", "backend.cli", "create-user", "loginuser", "loginpass"],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_DIR),
        env=env,
        timeout=30,
    )

    # Need to reinitialize the DB tables for the ASGI app since the CLI
    # created the DB externally. We use the transport approach.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            "/api/auth/login",
            json={"username": "loginuser", "password": "loginpass"},
        )
        ok = resp.status_code == 200
        body = resp.json()
        has_user = "user" in body and body["user"].get("username") == "loginuser"
        has_cookie = "session_id" in resp.cookies

        _record(
            "login_correct_creds_200",
            ok,
            f"status={resp.status_code}",
        )
        _record(
            "login_returns_user_object",
            has_user,
            f"body={body}",
        )
        _record(
            "login_sets_session_cookie",
            has_cookie,
            f"cookies={dict(resp.cookies)}",
        )


async def test_login_wrong_creds() -> None:
    """POST /api/auth/login with wrong creds returns 401."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            "/api/auth/login",
            json={"username": "loginuser", "password": "wrongpass"},
        )
        _record(
            "login_wrong_creds_401",
            resp.status_code == 401,
            f"status={resp.status_code}",
        )


async def test_me_with_session() -> None:
    """GET /api/auth/me with valid session cookie returns user data."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Login first to get cookie
        login_resp = await client.post(
            "/api/auth/login",
            json={"username": "loginuser", "password": "loginpass"},
        )
        # httpx AsyncClient tracks cookies automatically
        me_resp = await client.get("/api/auth/me")
        ok = me_resp.status_code == 200
        body = me_resp.json()
        has_user = "user" in body and body["user"].get("username") == "loginuser"
        _record(
            "me_with_session_200",
            ok,
            f"status={me_resp.status_code}",
        )
        _record(
            "me_returns_user_data",
            has_user,
            f"body={body}",
        )


async def test_me_without_session() -> None:
    """GET /api/auth/me without cookie returns 401."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/auth/me")
        _record(
            "me_without_session_401",
            resp.status_code == 401,
            f"status={resp.status_code}",
        )


async def test_logout_clears_session() -> None:
    """POST /api/auth/logout clears session; subsequent /me returns 401."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Login
        await client.post(
            "/api/auth/login",
            json={"username": "loginuser", "password": "loginpass"},
        )
        # Logout
        logout_resp = await client.post("/api/auth/logout")
        _record(
            "logout_returns_ok",
            logout_resp.status_code == 200,
            f"status={logout_resp.status_code}",
        )
        # /me after logout should be 401
        me_resp = await client.get("/api/auth/me")
        _record(
            "me_after_logout_401",
            me_resp.status_code == 401,
            f"status={me_resp.status_code}",
        )


async def test_full_roundtrip() -> None:
    """Full round-trip: create user via CLI, login, /me, logout, verify 401."""
    # Use a unique username to avoid conflicts with earlier tests.
    # Do NOT cleanup the DB here -- the ASGI app's engine shares the same
    # file and deleting it mid-run breaks the connection pool.
    python = str(_BACKEND_DIR / ".venv" / "bin" / "python")
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{_TEST_DB_PATH}"}
    result = subprocess.run(
        [python, "-m", "backend.cli", "create-user", "roundtrip", "rtpass"],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_DIR),
        env=env,
        timeout=30,
    )
    cli_ok = result.returncode == 0
    _record("roundtrip_cli_create", cli_ok, f"rc={result.returncode} stderr={result.stderr!r}")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Login
        login_resp = await client.post(
            "/api/auth/login",
            json={"username": "roundtrip", "password": "rtpass"},
        )
        _record(
            "roundtrip_login_200",
            login_resp.status_code == 200,
            f"status={login_resp.status_code} body={login_resp.text}",
        )

        # /me
        me_resp = await client.get("/api/auth/me")
        _record(
            "roundtrip_me_200",
            me_resp.status_code == 200 and me_resp.json().get("user", {}).get("username") == "roundtrip",
            f"status={me_resp.status_code} body={me_resp.text}",
        )

        # Logout
        logout_resp = await client.post("/api/auth/logout")
        _record(
            "roundtrip_logout_ok",
            logout_resp.status_code == 200,
            f"status={logout_resp.status_code}",
        )

        # /me after logout -> 401
        me2_resp = await client.get("/api/auth/me")
        _record(
            "roundtrip_me_after_logout_401",
            me2_resp.status_code == 401,
            f"status={me2_resp.status_code}",
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all() -> None:
    tests = [
        test_cli_create_user,
        test_login_success,
        test_login_wrong_creds,
        test_me_with_session,
        test_me_without_session,
        test_logout_clears_session,
        test_full_roundtrip,
    ]
    print("=" * 60)
    print("Phase 2 E2E: Authentication")
    print("=" * 60)

    for test_fn in tests:
        print(f"\n--- {test_fn.__name__} ---")
        try:
            await test_fn()
        except Exception as exc:
            _record(test_fn.__name__, False, f"EXCEPTION: {exc}\n{traceback.format_exc()}")

    print("\n" + "=" * 60)
    print(f"Results: {len(_passed)} passed, {len(_failed)} failed")
    if _failed:
        print("\nFailures:")
        for name, detail in _failed:
            print(f"  - {name}: {detail}")
    print("=" * 60)


def main() -> None:
    try:
        asyncio.run(run_all())
    finally:
        _cleanup_db()

    if _failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
