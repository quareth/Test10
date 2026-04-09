"""Async page fetcher with concurrency limiting and per-page timeouts."""

from __future__ import annotations

import asyncio

import httpx

from backend.schemas import FetchResult

_PER_PAGE_TIMEOUT = 15.0  # seconds


async def _fetch_one(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
) -> FetchResult:
    """Fetch a single URL, recording any failure in the result."""
    async with semaphore:
        try:
            response = await client.get(url, timeout=_PER_PAGE_TIMEOUT)
            return FetchResult(
                url=url,
                html=response.text,
                status_code=response.status_code,
                error=None,
                success=response.status_code < 400,
            )
        except httpx.TimeoutException:
            return FetchResult(
                url=url,
                html=None,
                status_code=None,
                error="Timeout after 15 seconds",
                success=False,
            )
        except httpx.HTTPError as exc:
            return FetchResult(
                url=url,
                html=None,
                status_code=None,
                error=str(exc),
                success=False,
            )
        except Exception as exc:  # noqa: BLE001
            return FetchResult(
                url=url,
                html=None,
                status_code=None,
                error=f"Unexpected error: {exc}",
                success=False,
            )


async def fetch_pages(
    urls: list[str],
    concurrency: int = 10,
) -> list[FetchResult]:
    """Fetch multiple pages concurrently with connection pooling.

    Args:
        urls: List of URLs to fetch.
        concurrency: Maximum number of concurrent requests (default 10).

    Returns:
        One FetchResult per input URL, in the same order.
    """
    if not urls:
        return []

    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:
        tasks = [_fetch_one(client, url, semaphore) for url in urls]
        results = await asyncio.gather(*tasks)

    return list(results)
