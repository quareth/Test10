"""Tests for backend.scraping.fetcher."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.scraping.fetcher import fetch_pages


def _run(coro):
    """Run an async coroutine."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _mock_response(status_code: int = 200, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Successful fetch returns FetchResult with HTML
# ---------------------------------------------------------------------------


class TestFetchPagesSuccess:
    def test_successful_fetch(self):
        resp = _mock_response(200, "<html>Hello</html>")

        async def fake_get(url, **kwargs):
            return resp

        with patch("backend.scraping.fetcher.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            results = _run(fetch_pages(["https://example.com/page"]))

        assert len(results) == 1
        r = results[0]
        assert r.url == "https://example.com/page"
        assert r.html == "<html>Hello</html>"
        assert r.status_code == 200
        assert r.success is True
        assert r.error is None


# ---------------------------------------------------------------------------
# Individual HTTP errors captured without aborting batch
# ---------------------------------------------------------------------------


class TestFetchPagesHttpError:
    def test_error_captured_per_page(self):
        call_count = 0

        async def fake_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "bad" in url:
                raise httpx.HTTPStatusError(
                    "Server error",
                    request=MagicMock(),
                    response=MagicMock(),
                )
            return _mock_response(200, "<html>OK</html>")

        with patch("backend.scraping.fetcher.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            results = _run(fetch_pages([
                "https://example.com/good",
                "https://example.com/bad",
                "https://example.com/also-good",
            ]))

        assert len(results) == 3
        # Good pages succeed
        assert results[0].success is True
        assert results[2].success is True
        # Bad page captured error, did not abort
        assert results[1].success is False
        assert results[1].error is not None


# ---------------------------------------------------------------------------
# Timeout captured in FetchResult.error
# ---------------------------------------------------------------------------


class TestFetchPagesTimeout:
    def test_timeout_captured(self):
        async def fake_get(url, **kwargs):
            raise httpx.ReadTimeout("timed out")

        with patch("backend.scraping.fetcher.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            results = _run(fetch_pages(["https://example.com/slow"]))

        assert len(results) == 1
        r = results[0]
        assert r.success is False
        assert r.error is not None
        assert "imeout" in r.error  # "Timeout after 15 seconds"
        assert r.html is None


# ---------------------------------------------------------------------------
# Empty URL list returns empty list
# ---------------------------------------------------------------------------


class TestFetchPagesEmpty:
    def test_empty_urls(self):
        results = _run(fetch_pages([]))
        assert results == []


# ---------------------------------------------------------------------------
# Concurrency semaphore limiting
# ---------------------------------------------------------------------------


class TestFetchPagesConcurrency:
    def test_semaphore_limits_concurrency(self):
        """Verify that at most `concurrency` fetches run simultaneously."""
        peak = 0
        current = 0

        async def fake_get(url, **kwargs):
            nonlocal peak, current
            current += 1
            if current > peak:
                peak = current
            await asyncio.sleep(0.01)
            current -= 1
            return _mock_response(200, "<html>OK</html>")

        with patch("backend.scraping.fetcher.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            urls = [f"https://example.com/{i}" for i in range(20)]
            results = _run(fetch_pages(urls, concurrency=3))

        assert len(results) == 20
        assert all(r.success for r in results)
        # Peak concurrency should not exceed the limit
        assert peak <= 3
