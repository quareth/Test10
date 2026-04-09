"""
Phase 2 E2E tests: Schedule CRUD lifecycle.

Tests the full schedule CRUD flow against the real ASGI app with an isolated
temporary SQLite database. No external server process needed -- httpx
speaks ASGI directly.

Covers:
- Create a user (CLI), login, create a target
- POST /api/targets/{id}/schedule  (create schedule)
- GET  /api/targets/{id}/schedule  (read schedule)
- PATCH /api/targets/{id}/schedule (toggle pause/active)
- DELETE /api/targets/{id}/schedule (delete schedule)
- Auth guards: unauthenticated requests return 401
- 404 for non-existent target schedule operations

Usage:
    cd /path/to/project
    PYTHONPATH=backend .venv/bin/python backend/tests/e2e/test_phase2_schedule_crud_e2e.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Isolated DB setup -- must happen before any backend import so the Settings
# singleton picks up the override.
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_TEST_DB_PATH = _BACKEND_DIR / "test_schedule_e2e.db"

# Ensure the backend package is importable
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Force a temporary database for isolation
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"

import httpx  # noqa: E402

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
# Setup: create user via CLI, return logged-in client with target_id
# ---------------------------------------------------------------------------

async def _setup_authenticated_client_with_target(
    client: httpx.AsyncClient,
) -> int:
    """Login and create a target. Return the target id."""
    # Login
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "scheduser", "password": "schedpass"},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"

    # Create a target
    target_resp = await client.post(
        "/api/targets",
        json={"url": "https://example.com/sitemap.xml", "name": "Schedule Test Site"},
    )
    assert target_resp.status_code == 201, f"Create target failed: {target_resp.text}"
    target_id = target_resp.json()["target"]["id"]
    return target_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_schedule_crud_lifecycle() -> None:
    """Full CRUD lifecycle: create, read, toggle pause, toggle active, delete."""
    _cleanup_db()

    # Seed user via CLI
    python = str(_BACKEND_DIR / ".venv" / "bin" / "python")
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{_TEST_DB_PATH}"}
    result = subprocess.run(
        [python, "-m", "backend.cli", "create-user", "scheduser", "schedpass"],
        capture_output=True, text=True, cwd=str(_BACKEND_DIR), env=env, timeout=30,
    )
    _record("setup_cli_create_user", result.returncode == 0,
            f"rc={result.returncode} stderr={result.stderr!r}")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        target_id = await _setup_authenticated_client_with_target(client)

        # --- 1. CREATE schedule (daily) ---
        create_resp = await client.post(
            f"/api/targets/{target_id}/schedule",
            json={"interval_type": "daily"},
        )
        _record(
            "create_schedule_200",
            create_resp.status_code == 200,
            f"status={create_resp.status_code} body={create_resp.text}",
        )
        body = create_resp.json()
        schedule = body.get("schedule")
        _record(
            "create_schedule_has_fields",
            schedule is not None
            and schedule.get("interval_type") == "daily"
            and schedule.get("status") == "active"
            and schedule.get("target_id") == target_id
            and "id" in schedule
            and "created_at" in schedule
            and "updated_at" in schedule,
            f"schedule={schedule}",
        )
        schedule_id = schedule["id"] if schedule else None

        # --- 2. READ schedule ---
        get_resp = await client.get(f"/api/targets/{target_id}/schedule")
        _record(
            "get_schedule_200",
            get_resp.status_code == 200,
            f"status={get_resp.status_code}",
        )
        get_body = get_resp.json()
        get_sched = get_body.get("schedule")
        _record(
            "get_schedule_matches_created",
            get_sched is not None
            and get_sched.get("id") == schedule_id
            and get_sched.get("interval_type") == "daily"
            and get_sched.get("status") == "active",
            f"schedule={get_sched}",
        )

        # --- 3. TOGGLE to paused ---
        pause_resp = await client.patch(
            f"/api/targets/{target_id}/schedule",
            json={"status": "paused"},
        )
        _record(
            "toggle_pause_200",
            pause_resp.status_code == 200,
            f"status={pause_resp.status_code}",
        )
        pause_sched = pause_resp.json().get("schedule")
        _record(
            "toggle_pause_status_is_paused",
            pause_sched is not None and pause_sched.get("status") == "paused",
            f"schedule={pause_sched}",
        )

        # --- 4. Verify pause persisted via GET ---
        get_paused_resp = await client.get(f"/api/targets/{target_id}/schedule")
        paused_sched = get_paused_resp.json().get("schedule")
        _record(
            "get_after_pause_status_paused",
            paused_sched is not None and paused_sched.get("status") == "paused",
            f"schedule={paused_sched}",
        )

        # --- 5. TOGGLE back to active ---
        resume_resp = await client.patch(
            f"/api/targets/{target_id}/schedule",
            json={"status": "active"},
        )
        _record(
            "toggle_active_200",
            resume_resp.status_code == 200,
            f"status={resume_resp.status_code}",
        )
        resume_sched = resume_resp.json().get("schedule")
        _record(
            "toggle_active_status_is_active",
            resume_sched is not None and resume_sched.get("status") == "active",
            f"schedule={resume_sched}",
        )

        # --- 6. DELETE schedule ---
        delete_resp = await client.delete(f"/api/targets/{target_id}/schedule")
        _record(
            "delete_schedule_200",
            delete_resp.status_code == 200,
            f"status={delete_resp.status_code}",
        )
        delete_body = delete_resp.json()
        _record(
            "delete_schedule_ok_true",
            delete_body.get("ok") is True,
            f"body={delete_body}",
        )

        # --- 7. GET after delete returns null ---
        get_deleted_resp = await client.get(f"/api/targets/{target_id}/schedule")
        _record(
            "get_after_delete_returns_null",
            get_deleted_resp.status_code == 200
            and get_deleted_resp.json().get("schedule") is None,
            f"status={get_deleted_resp.status_code} body={get_deleted_resp.text}",
        )

        # --- 8. DELETE again returns 404 ---
        delete_again_resp = await client.delete(f"/api/targets/{target_id}/schedule")
        _record(
            "delete_again_returns_404",
            delete_again_resp.status_code == 404,
            f"status={delete_again_resp.status_code}",
        )


async def test_schedule_cron_type() -> None:
    """Create a schedule with cron interval_type and cron_expression."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        target_id = await _setup_authenticated_client_with_target(client)

        resp = await client.post(
            f"/api/targets/{target_id}/schedule",
            json={"interval_type": "cron", "cron_expression": "0 6 * * *"},
        )
        _record(
            "create_cron_schedule_200",
            resp.status_code == 200,
            f"status={resp.status_code}",
        )
        sched = resp.json().get("schedule")
        _record(
            "cron_schedule_fields",
            sched is not None
            and sched.get("interval_type") == "cron"
            and sched.get("cron_expression") == "0 6 * * *",
            f"schedule={sched}",
        )


async def test_schedule_validation_errors() -> None:
    """Invalid schedule payloads return 422."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        target_id = await _setup_authenticated_client_with_target(client)

        # Invalid interval_type
        resp1 = await client.post(
            f"/api/targets/{target_id}/schedule",
            json={"interval_type": "invalid_type"},
        )
        _record(
            "invalid_interval_type_422",
            resp1.status_code == 422,
            f"status={resp1.status_code}",
        )

        # Cron without expression
        resp2 = await client.post(
            f"/api/targets/{target_id}/schedule",
            json={"interval_type": "cron"},
        )
        _record(
            "cron_without_expression_422",
            resp2.status_code == 422,
            f"status={resp2.status_code}",
        )

        # Invalid toggle status
        # First create a valid schedule to toggle
        await client.post(
            f"/api/targets/{target_id}/schedule",
            json={"interval_type": "daily"},
        )
        resp3 = await client.patch(
            f"/api/targets/{target_id}/schedule",
            json={"status": "invalid_status"},
        )
        _record(
            "invalid_toggle_status_422",
            resp3.status_code == 422,
            f"status={resp3.status_code}",
        )


async def test_schedule_auth_guard() -> None:
    """Unauthenticated requests to schedule endpoints return 401."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # No login -- should get 401 on all schedule endpoints
        resp_post = await client.post(
            "/api/targets/1/schedule",
            json={"interval_type": "daily"},
        )
        _record("unauth_create_401", resp_post.status_code == 401,
                f"status={resp_post.status_code}")

        resp_get = await client.get("/api/targets/1/schedule")
        _record("unauth_get_401", resp_get.status_code == 401,
                f"status={resp_get.status_code}")

        resp_patch = await client.patch(
            "/api/targets/1/schedule",
            json={"status": "paused"},
        )
        _record("unauth_patch_401", resp_patch.status_code == 401,
                f"status={resp_patch.status_code}")

        resp_delete = await client.delete("/api/targets/1/schedule")
        _record("unauth_delete_401", resp_delete.status_code == 401,
                f"status={resp_delete.status_code}")


async def test_schedule_nonexistent_target() -> None:
    """Schedule operations on a non-existent target return 404."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Login
        await client.post(
            "/api/auth/login",
            json={"username": "scheduser", "password": "schedpass"},
        )

        resp_post = await client.post(
            "/api/targets/99999/schedule",
            json={"interval_type": "daily"},
        )
        _record("nonexist_target_create_404", resp_post.status_code == 404,
                f"status={resp_post.status_code}")

        resp_get = await client.get("/api/targets/99999/schedule")
        _record("nonexist_target_get_404", resp_get.status_code == 404,
                f"status={resp_get.status_code}")

        resp_patch = await client.patch(
            "/api/targets/99999/schedule",
            json={"status": "paused"},
        )
        _record("nonexist_target_patch_404", resp_patch.status_code == 404,
                f"status={resp_patch.status_code}")

        resp_delete = await client.delete("/api/targets/99999/schedule")
        _record("nonexist_target_delete_404", resp_delete.status_code == 404,
                f"status={resp_delete.status_code}")


async def test_schedule_upsert_behavior() -> None:
    """Creating a schedule twice on the same target updates (upserts) rather than duplicating."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        target_id = await _setup_authenticated_client_with_target(client)

        # Create with daily
        resp1 = await client.post(
            f"/api/targets/{target_id}/schedule",
            json={"interval_type": "daily"},
        )
        sched1 = resp1.json().get("schedule")
        sched1_id = sched1["id"] if sched1 else None

        # Create again with 6h -- should update same record
        resp2 = await client.post(
            f"/api/targets/{target_id}/schedule",
            json={"interval_type": "6h"},
        )
        sched2 = resp2.json().get("schedule")
        _record(
            "upsert_same_id",
            sched2 is not None and sched2.get("id") == sched1_id,
            f"first_id={sched1_id} second_id={sched2.get('id') if sched2 else None}",
        )
        _record(
            "upsert_updated_interval",
            sched2 is not None and sched2.get("interval_type") == "6h",
            f"interval_type={sched2.get('interval_type') if sched2 else None}",
        )


async def test_target_list_includes_schedule_info() -> None:
    """GET /api/targets returns has_schedule and schedule_status fields."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        target_id = await _setup_authenticated_client_with_target(client)

        # Before schedule: has_schedule should be false
        targets_resp = await client.get("/api/targets")
        targets = targets_resp.json().get("targets", [])
        our_target = next((t for t in targets if t["id"] == target_id), None)
        _record(
            "list_targets_no_schedule",
            our_target is not None
            and our_target.get("has_schedule") is False
            and our_target.get("schedule_status") is None,
            f"target={our_target}",
        )

        # Create schedule
        await client.post(
            f"/api/targets/{target_id}/schedule",
            json={"interval_type": "daily"},
        )

        # After schedule: has_schedule should be true
        targets_resp2 = await client.get("/api/targets")
        targets2 = targets_resp2.json().get("targets", [])
        our_target2 = next((t for t in targets2 if t["id"] == target_id), None)
        _record(
            "list_targets_with_schedule",
            our_target2 is not None
            and our_target2.get("has_schedule") is True
            and our_target2.get("schedule_status") == "active",
            f"target={our_target2}",
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all() -> None:
    tests = [
        test_schedule_crud_lifecycle,
        test_schedule_cron_type,
        test_schedule_validation_errors,
        test_schedule_auth_guard,
        test_schedule_nonexistent_target,
        test_schedule_upsert_behavior,
        test_target_list_includes_schedule_info,
    ]
    print("=" * 60)
    print("Phase 2 E2E: Schedule CRUD")
    print("=" * 60)

    for test_fn in tests:
        print(f"\n--- {test_fn.__name__} ---")
        try:
            await test_fn()
        except Exception as exc:
            _record(test_fn.__name__, False,
                    f"EXCEPTION: {exc}\n{traceback.format_exc()}")

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
