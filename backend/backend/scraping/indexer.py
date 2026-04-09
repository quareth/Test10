"""Index assembler: bulk and structured output from scraped pages."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.schemas import PageContent

logger = logging.getLogger(__name__)

# Regex: keep only alphanumeric, dot, hyphen, underscore
_SAFE_CHAR_RE = re.compile(r"[^a-zA-Z0-9._\-]")

_MAX_SEGMENT_LEN = 100


def _sanitize_segment(segment: str) -> str:
    """Sanitize a single path segment.

    - Replace unsafe characters with underscores.
    - Strip leading/trailing dots and whitespace.
    - Reject traversal segments ('..').
    - Truncate to 100 characters.
    """
    if segment == "..":
        return ""
    cleaned = _SAFE_CHAR_RE.sub("_", segment)
    cleaned = cleaned.strip(". ")
    if not cleaned:
        return ""
    return cleaned[:_MAX_SEGMENT_LEN]


def _url_path_to_fs_path(url_path: str) -> Path:
    """Convert a URL path to a sanitized relative filesystem path.

    Trailing slashes or empty paths produce index.md.
    """
    # Determine if path ends with a slash (before stripping)
    trailing_slash = url_path.endswith("/")

    # Strip slashes, split into segments
    stripped = url_path.strip("/")
    if not stripped:
        return Path("index.md")

    raw_segments = stripped.split("/")
    segments = [_sanitize_segment(seg) for seg in raw_segments]
    segments = [s for s in segments if s]

    if not segments:
        return Path("index.md")

    if trailing_slash:
        # Trailing slash means the last segment is a directory; use index.md inside it
        return Path(*segments) / "index.md"

    # Append .md to the final segment
    last = segments[-1]
    if not last.endswith(".md"):
        segments[-1] = last + ".md"

    return Path(*segments)


def assemble_bulk(pages: list[PageContent]) -> str:
    """Concatenate all pages into a single string with YAML-style frontmatter.

    Each page is preceded by:
        ---
        Source: {url}
        Scraped: {timestamp}
        ---
        {markdown content}
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts: list[str] = []
    for page in pages:
        frontmatter = (
            f"---\nSource: {page.url}\nScraped: {timestamp}\n---\n"
        )
        parts.append(frontmatter + page.markdown)
    return "\n".join(parts)


def assemble_structured(
    pages: list[PageContent], base_path: Path
) -> list[Path]:
    """Write each page as an individual .md file under base_path/structured/.

    Maps each page's url_path to a sanitized filesystem path.
    Returns the list of written file paths.
    """
    structured_root = base_path / "structured"
    written: list[Path] = []

    for page in pages:
        rel = _url_path_to_fs_path(page.url_path)
        target = structured_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page.markdown, encoding="utf-8")
        written.append(target)
        logger.debug("Wrote %s", target)

    return written
