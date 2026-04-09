"""
Wave-2 Phase 1 E2E tests: Database and Model Extensions.

Verifies that the new Schedule, Session models and ScrapeJob.trigger column
are created correctly, that schemas import and validate, and that the
config exposes the new settings. Runs against a real isolated SQLite DB
via the ASGI transport (no external server needed).

Usage:

    PYTHONPATH=backend .venv/bin/python backend/tests/e2e/test_phase1_models_e2e.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Isolated DB setup -- must happen before any backend import.
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_TEST_DB_PATH = _BACKEND_DIR / "test_phase1_e2e.db"

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

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
# Tests
# ---------------------------------------------------------------------------

async def test_schedule_model_columns() -> None:
    """Schedule model has all expected columns after table creation."""
    from backend.models import Schedule

    cols = {c.name for c in Schedule.__table__.columns}
    expected = {
        "id", "target_id", "interval_type", "cron_expression",
        "status", "next_run_at", "last_run_at", "last_run_status",
        "created_at", "updated_at",
    }
    missing = expected - cols
    _record(
        "schedule_model_columns",
        not missing,
        f"missing={missing}" if missing else "",
    )


async def test_session_model_columns() -> None:
    """Session model has all expected columns."""
    from backend.models import Session

    cols = {c.name for c in Session.__table__.columns}
    expected = {"session_id", "user_id", "created_at", "expires_at"}
    missing = expected - cols
    _record(
        "session_model_columns",
        not missing,
        f"missing={missing}" if missing else "",
    )


async def test_scrape_job_trigger_column() -> None:
    """ScrapeJob model includes the new trigger column."""
    from backend.models import ScrapeJob

    cols = {c.name for c in ScrapeJob.__table__.columns}
    _record(
        "scrape_job_trigger_column",
        "trigger" in cols,
        f"columns={cols}",
    )


async def test_tables_created_in_db() -> None:
    """init_db creates schedules and sessions tables in the actual database."""
    from backend.database import init_db, engine

    _cleanup_db()
    await init_db()

    from sqlalchemy import inspect as sa_inspect

    async with engine.connect() as conn:
        def get_tables(sync_conn):
            return sa_inspect(sync_conn).get_table_names()

        tables = await conn.run_sync(get_tables)

    _record(
        "schedules_table_exists",
        "schedules" in tables,
        f"tables={tables}",
    )
    _record(
        "sessions_table_exists",
        "sessions" in tables,
        f"tables={tables}",
    )


async def test_db_trigger_column_present() -> None:
    """The trigger column is physically present in the scrape_jobs table."""
    from backend.database import engine
    from sqlalchemy import inspect as sa_inspect

    async with engine.connect() as conn:
        def get_cols(sync_conn):
            insp = sa_inspect(sync_conn)
            return [c["name"] for c in insp.get_columns("scrape_jobs")]

        cols = await conn.run_sync(get_cols)

    _record(
        "db_trigger_column_present",
        "trigger" in cols,
        f"columns={cols}",
    )


async def test_schedule_schemas_import() -> None:
    """ScheduleCreate, ScheduleOut, ScheduleToggle import without error."""
    try:
        from backend.schemas import ScheduleCreate, ScheduleOut, ScheduleToggle
        _record("schedule_schemas_import", True)
    except ImportError as e:
        _record("schedule_schemas_import", False, str(e))


async def test_schedule_create_validation() -> None:
    """ScheduleCreate accepts valid data and rejects bad interval_type."""
    from backend.schemas import ScheduleCreate

    # Valid creation (target_id is set from route, not in schema body)
    try:
        sc = ScheduleCreate(interval_type="daily")
        ok = sc.interval_type == "daily"
        _record("schedule_create_valid", ok, f"got={sc.model_dump()}")
    except Exception as e:
        _record("schedule_create_valid", False, str(e))

    # Invalid interval_type should fail validation
    try:
        sc_bad = ScheduleCreate(interval_type="every_second")
        _record("schedule_create_invalid_rejected", False, f"accepted invalid: {sc_bad.model_dump()}")
    except Exception:
        _record("schedule_create_invalid_rejected", True)


async def test_config_new_fields() -> None:
    """Settings exposes SECRET_KEY and ALLOWED_ORIGINS."""
    from backend.config import Settings

    s = Settings()
    has_secret = hasattr(s, "SECRET_KEY") and isinstance(s.SECRET_KEY, str) and len(s.SECRET_KEY) > 0
    has_origins = hasattr(s, "ALLOWED_ORIGINS")

    _record("config_secret_key", has_secret, f"SECRET_KEY={getattr(s, 'SECRET_KEY', 'MISSING')!r}")
    _record("config_allowed_origins", has_origins, f"ALLOWED_ORIGINS={getattr(s, 'ALLOWED_ORIGINS', 'MISSING')!r}")


async def test_app_startup_lifespan() -> None:
    """The ASGI app starts up without error (lifespan runs init_db)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Any route -- even a 404 -- proves the app booted
        resp = await client.get("/api/health")
        # Accept 200 or 404 (route may not exist yet) -- either proves startup worked
        ok = resp.status_code in (200, 404)
        _record(
            "app_startup_lifespan",
            ok,
            f"status={resp.status_code}",
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all() -> None:
    tests = [
        test_schedule_model_columns,
        test_session_model_columns,
        test_scrape_job_trigger_column,
        test_tables_created_in_db,
        test_db_trigger_column_present,
        test_schedule_schemas_import,
        test_schedule_create_validation,
        test_config_new_fields,
        test_app_startup_lifespan,
    ]
    print("=" * 60)
    print("Wave-2 Phase 1 E2E: Database and Model Extensions")
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
