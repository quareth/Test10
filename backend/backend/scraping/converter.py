"""HTML-to-Markdown converter with chrome stripping."""

from __future__ import annotations

import logging

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify

logger = logging.getLogger(__name__)

_STRIP_TAGS = {"nav", "header", "footer", "script", "style"}
_STRIP_ROLES = {"navigation", "banner", "contentinfo"}
_SIDEBAR_HINTS = {"sidebar", "side-bar", "aside"}


def _is_sidebar(tag: Tag) -> bool:
    """Return True if the tag looks like a sidebar element."""
    if tag.name == "aside":
        return True
    classes = tag.get("class") or []
    tag_id = tag.get("id") or ""
    text = " ".join(classes).lower() + " " + tag_id.lower()
    return any(hint in text for hint in _SIDEBAR_HINTS)


def _strip_chrome(soup: BeautifulSoup) -> None:
    """Remove navigation, header, footer, sidebar, script, and style elements."""
    # Strip by tag name
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    # Strip by ARIA role
    for role in _STRIP_ROLES:
        for tag in soup.find_all(attrs={"role": role}):
            tag.decompose()

    # Strip sidebars (aside tags and elements with sidebar-ish classes/ids)
    for tag in soup.find_all(_is_sidebar):
        tag.decompose()


def _find_main_content(soup: BeautifulSoup) -> Tag | None:
    """Find the main content container, preferring semantic elements."""
    # Prefer <main>
    main = soup.find("main")
    if main:
        return main

    # Try <article>
    article = soup.find("article")
    if article:
        return article

    # Try role="main"
    role_main = soup.find(attrs={"role": "main"})
    if role_main:
        return role_main

    # Fall back to <body>
    body = soup.find("body")
    if body:
        return body

    return None


def convert_html(html: str, source_url: str) -> str:
    """Convert an HTML document to Markdown.

    Extracts the main content area, strips navigation chrome,
    and converts the remaining HTML to Markdown.

    Args:
        html: Raw HTML string.
        source_url: The URL the HTML was fetched from (used for logging).

    Returns:
        Markdown string, or empty string if the input is empty/unparseable.
    """
    if not isinstance(html, str) or not html.strip():
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")

        content = _find_main_content(soup)
        if content is None:
            logger.debug("No content container found for %s", source_url)
            return ""

        _strip_chrome(content)

        inner_html = content.decode_contents()
        if not inner_html.strip():
            return ""

        md = markdownify(inner_html, heading_style="ATX", strip=["img"])
        # Collapse excessive blank lines
        lines = md.splitlines()
        cleaned: list[str] = []
        blank_count = 0
        for line in lines:
            if not line.strip():
                blank_count += 1
                if blank_count <= 2:
                    cleaned.append("")
            else:
                blank_count = 0
                cleaned.append(line)

        result = "\n".join(cleaned).strip()
        return result

    except Exception:
        logger.exception("Failed to convert HTML from %s", source_url)
        return ""
