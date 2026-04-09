"""Tests for backend.scraping.orchestrator."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.schemas import FetchResult, PageContent, ScrapeResult


# ---------------------------------------------------------------------------
# Helpers to build fake Target / ScrapeJob / AsyncSession
# ---------------------------------------------------------------------------

def _make_target(id_: int = 1, url: str = "https://example.com") -> SimpleNamespace:
    return SimpleNamespace(id=id_, url=url)


def _make_job(id_: int = 10, target_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_,
        target_id=target_id,
        status="pending",
        pages_found=0,
        pages_scraped=0,
        started_at=None,
        completed_at=None,
        error_message=None,
    )


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def _run(coro):
    """Run an async coroutine in a new event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Patches target the orchestrator module's imported names
# ---------------------------------------------------------------------------
_MOD = "backend.scraping.orchestrator"


# ---------------------------------------------------------------------------
# Success flow
# ---------------------------------------------------------------------------

class TestRunScrapeSuccess:
    """Full pipeline completes with correct state transitions."""

    def test_success_flow(self, tmp_path: Path):
        target = _make_target()
        job = _make_job()
        db = _make_db()

        urls = ["https://example.com/a", "https://example.com/b"]
        fetch_results = [
            FetchResult(url="https://example.com/a", html="<main>Hello</main>", status_code=200, error=None, success=True),
            FetchResult(url="https://example.com/b", html="<main>World</main>", status_code=200, error=None, success=True),
        ]

        data_dir = str(tmp_path)

        with (
            patch(f"{_MOD}.parse_sitemap", new_callable=AsyncMock, return_value=urls),
            patch(f"{_MOD}.fetch_pages", new_callable=AsyncMock, return_value=fetch_results),
            patch(f"{_MOD}.convert_html", side_effect=lambda html, url: f"md:{url}"),
            patch(f"{_MOD}.settings") as mock_settings,
        ):
            mock_settings.DATA_DIR = data_dir

            from backend.scraping.orchestrator import run_scrape
            result: ScrapeResult = _run(run_scrape(target, job, db))

        assert result.status == "complete"
        assert result.pages_found == 2
        assert result.pages_scraped == 2
        assert result.pages_failed == 0
        assert result.snapshot_path is not None
        assert result.error_message is None
        assert result.job_id == job.id

        # Job status transitions
        assert job.status == "complete"
        assert job.pages_found == 2
        assert job.pages_scraped == 2
        assert job.completed_at is not None

        # DB operations: add was called for Snapshot
        db.add.assert_called_once()
        snapshot_arg = db.add.call_args[0][0]
        assert snapshot_arg.job_id == job.id
        assert snapshot_arg.file_count >= 1
        assert snapshot_arg.total_size_bytes > 0

        # Verify files on disk
        snapshot_full_path = tmp_path / result.snapshot_path
        assert (snapshot_full_path / "bulk.md").exists()
        assert (snapshot_full_path / "structured").is_dir()


# ---------------------------------------------------------------------------
# SitemapError -> failed
# ---------------------------------------------------------------------------

class TestRunScrapeSitemapError:
    """SitemapError during parse_sitemap leads to failed job."""

    def test_sitemap_error_fails_job(self, tmp_path: Path):
        from backend.scraping.sitemap import SitemapError

        target = _make_target()
        job = _make_job()
        db = _make_db()

        with (
            patch(f"{_MOD}.parse_sitemap", new_callable=AsyncMock, side_effect=SitemapError("No sitemap")),
            patch(f"{_MOD}.settings") as mock_settings,
        ):
            mock_settings.DATA_DIR = str(tmp_path)

            from backend.scraping.orchestrator import run_scrape
            result: ScrapeResult = _run(run_scrape(target, job, db))

        assert result.status == "failed"
        assert "No sitemap" in result.error_message
        assert job.status == "failed"
        assert job.error_message == "No sitemap"
        assert job.completed_at is not None


# ---------------------------------------------------------------------------
# Unexpected exception -> failed without crashing
# ---------------------------------------------------------------------------

class TestRunScrapeUnexpectedError:
    """Unexpected exception in pipeline results in failed status, not crash."""

    def test_unexpected_exception_fails_job(self, tmp_path: Path):
        target = _make_target()
        job = _make_job()
        db = _make_db()

        with (
            patch(f"{_MOD}.parse_sitemap", new_callable=AsyncMock, side_effect=RuntimeError("kaboom")),
            patch(f"{_MOD}.settings") as mock_settings,
        ):
            mock_settings.DATA_DIR = str(tmp_path)

            from backend.scraping.orchestrator import run_scrape
            result: ScrapeResult = _run(run_scrape(target, job, db))

        assert result.status == "failed"
        assert "kaboom" in result.error_message
        assert job.status == "failed"


# ---------------------------------------------------------------------------
# Partial fetch failure
# ---------------------------------------------------------------------------

class TestRunScrapePartialFetch:
    """Some fetches fail; pages_scraped reflects only successful conversions."""

    def test_partial_fetch_counts(self, tmp_path: Path):
        target = _make_target()
        job = _make_job()
        db = _make_db()

        urls = ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
        fetch_results = [
            FetchResult(url="https://example.com/a", html="<main>OK</main>", status_code=200, error=None, success=True),
            FetchResult(url="https://example.com/b", html=None, status_code=None, error="Timeout", success=False),
            FetchResult(url="https://example.com/c", html="<main>Also OK</main>", status_code=200, error=None, success=True),
        ]

        with (
            patch(f"{_MOD}.parse_sitemap", new_callable=AsyncMock, return_value=urls),
            patch(f"{_MOD}.fetch_pages", new_callable=AsyncMock, return_value=fetch_results),
            patch(f"{_MOD}.convert_html", side_effect=lambda html, url: f"md:{url}"),
            patch(f"{_MOD}.settings") as mock_settings,
        ):
            mock_settings.DATA_DIR = str(tmp_path)

            from backend.scraping.orchestrator import run_scrape
            result: ScrapeResult = _run(run_scrape(target, job, db))

        assert result.status == "complete"
        assert result.pages_found == 3
        assert result.pages_scraped == 2
        assert result.pages_failed == 1


# ---------------------------------------------------------------------------
# Job status transitions: pending -> running -> complete
# ---------------------------------------------------------------------------

class TestStatusTransitions:
    """Verify the job object goes through the correct status sequence."""

    def test_status_sequence(self, tmp_path: Path):
        target = _make_target()
        job = _make_job()
        db = _make_db()
        statuses: list[str] = []

        original_commit = db.commit

        async def track_commit():
            statuses.append(job.status)
            return await original_commit()

        db.commit = track_commit

        urls = ["https://example.com/page"]
        fetch_results = [
            FetchResult(url="https://example.com/page", html="<main>Hi</main>", status_code=200, error=None, success=True),
        ]

        with (
            patch(f"{_MOD}.parse_sitemap", new_callable=AsyncMock, return_value=urls),
            patch(f"{_MOD}.fetch_pages", new_callable=AsyncMock, return_value=fetch_results),
            patch(f"{_MOD}.convert_html", return_value="# Hi"),
            patch(f"{_MOD}.settings") as mock_settings,
        ):
            mock_settings.DATA_DIR = str(tmp_path)

            from backend.scraping.orchestrator import run_scrape
            _run(run_scrape(target, job, db))

        # First commit: running. Then pages_found. Then pages_scraped.
        # Then snapshot. Then complete.
        assert statuses[0] == "running"
        assert statuses[-1] == "complete"


# ---------------------------------------------------------------------------
# Empty conversion results still complete (no pages scraped)
# ---------------------------------------------------------------------------

class TestEmptyConversion:
    """All fetches succeed but converter returns empty -> still completes."""

    def test_zero_pages_scraped(self, tmp_path: Path):
        target = _make_target()
        job = _make_job()
        db = _make_db()

        urls = ["https://example.com/a"]
        fetch_results = [
            FetchResult(url="https://example.com/a", html="<div></div>", status_code=200, error=None, success=True),
        ]

        with (
            patch(f"{_MOD}.parse_sitemap", new_callable=AsyncMock, return_value=urls),
            patch(f"{_MOD}.fetch_pages", new_callable=AsyncMock, return_value=fetch_results),
            patch(f"{_MOD}.convert_html", return_value=""),
            patch(f"{_MOD}.settings") as mock_settings,
        ):
            mock_settings.DATA_DIR = str(tmp_path)

            from backend.scraping.orchestrator import run_scrape
            result: ScrapeResult = _run(run_scrape(target, job, db))

        assert result.status == "complete"
        assert result.pages_found == 1
        assert result.pages_scraped == 0
