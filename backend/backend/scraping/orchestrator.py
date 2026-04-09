"""Scrape orchestrator: coordinates the full scraping pipeline end-to-end."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import Snapshot, ScrapeJob, Target
from backend.schemas import PageContent, ScrapeResult

from .converter import convert_html
from .fetcher import fetch_pages
from .indexer import assemble_bulk, assemble_structured
from .sitemap import SitemapError, parse_sitemap

logger = logging.getLogger(__name__)


async def _fail_job(
    job: ScrapeJob, error: str, db: AsyncSession
) -> ScrapeResult:
    """Mark a job as failed and return a failure ScrapeResult."""
    job.status = "failed"
    job.error_message = error
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return ScrapeResult(
        job_id=job.id,
        status="failed",
        pages_found=job.pages_found,
        pages_scraped=job.pages_scraped,
        pages_failed=0,
        snapshot_path=None,
        error_message=error,
    )


async def run_scrape(
    target: Target, job: ScrapeJob, db: AsyncSession
) -> ScrapeResult:
    """Run the full scraping pipeline for a target.

    Coordinates sitemap parsing, page fetching, HTML-to-Markdown conversion,
    index assembly, snapshot storage, and DB record creation.

    Args:
        target: The Target to scrape.
        job: A ScrapeJob in "pending" status.
        db: An async database session for status updates and record creation.

    Returns:
        ScrapeResult summarising the outcome.
    """
    try:
        # 1. Mark job as running
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        # 2. Discover URLs from sitemap
        try:
            urls = await parse_sitemap(target.url)
        except SitemapError as exc:
            return await _fail_job(job, str(exc), db)

        # 3. Record pages found
        job.pages_found = len(urls)
        await db.commit()

        # 4. Fetch all pages
        fetch_results = await fetch_pages(urls)

        # 5. Convert successful fetches to Markdown
        pages: list[PageContent] = []
        for result in fetch_results:
            if not result.success or not result.html:
                continue
            markdown = convert_html(result.html, result.url)
            if not markdown:
                continue
            url_path = urlparse(result.url).path
            pages.append(
                PageContent(url=result.url, url_path=url_path, markdown=markdown)
            )

        # 6. Record pages scraped
        job.pages_scraped = len(pages)
        await db.commit()

        # 7. Build snapshot storage path
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_dir = (
            Path(settings.DATA_DIR)
            / "snapshots"
            / str(target.id)
            / f"{job.id}_{timestamp}"
        )
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # 8. Write bulk.md
        bulk_content = assemble_bulk(pages)
        bulk_path = snapshot_dir / "bulk.md"
        bulk_path.write_text(bulk_content, encoding="utf-8")

        # 9. Write structured files
        structured_files = assemble_structured(pages, snapshot_dir)

        # 10. Calculate file_count and total_size_bytes
        file_count = 1 + len(structured_files)  # bulk.md + structured files
        total_size_bytes = bulk_path.stat().st_size
        for sf in structured_files:
            total_size_bytes += sf.stat().st_size

        # 11. Create Snapshot record
        # Store path relative to DATA_DIR for portability
        relative_path = str(snapshot_dir.relative_to(Path(settings.DATA_DIR)))
        snapshot = Snapshot(
            job_id=job.id,
            storage_path=relative_path,
            file_count=file_count,
            total_size_bytes=total_size_bytes,
        )
        db.add(snapshot)
        await db.commit()

        # 12. Mark job complete
        job.status = "complete"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # 13. Return success result
        pages_failed = sum(1 for r in fetch_results if not r.success)
        return ScrapeResult(
            job_id=job.id,
            status="complete",
            pages_found=job.pages_found,
            pages_scraped=job.pages_scraped,
            pages_failed=pages_failed,
            snapshot_path=relative_path,
            error_message=None,
        )

    except Exception as exc:
        # 14. Catch-all: mark job as failed without crashing
        logger.exception("Unexpected error in scrape pipeline for job %s", job.id)
        return await _fail_job(job, f"Unexpected error: {exc}", db)
