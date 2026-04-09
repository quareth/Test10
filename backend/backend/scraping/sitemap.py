"""Sitemap parser for discovering page URLs from a site's sitemap.xml."""

import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urlunparse

import httpx


class SitemapError(Exception):
    """Raised when sitemap fetching or parsing fails."""


_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_REQUEST_TIMEOUT = 30.0


def _normalize_url(url: str) -> str:
    """Strip query string and fragment from a URL."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


async def _fetch_xml(client: httpx.AsyncClient, url: str) -> ET.Element:
    """Fetch a URL and parse the response body as XML.

    Raises SitemapError on HTTP errors, timeouts, or malformed XML.
    """
    try:
        response = await client.get(url, follow_redirects=True)
    except httpx.TimeoutException:
        raise SitemapError(f"Timeout fetching sitemap: {url}")
    except httpx.HTTPError as exc:
        raise SitemapError(f"Network error fetching sitemap: {exc}")

    if response.status_code == 404:
        raise SitemapError(f"Sitemap not found at {url}")
    if response.status_code >= 400:
        raise SitemapError(
            f"HTTP {response.status_code} fetching sitemap: {url}"
        )

    try:
        return ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise SitemapError(f"Failed to parse sitemap: {exc}")


def _extract_urls_from_urlset(root: ET.Element) -> list[str]:
    """Extract <loc> URLs from a <urlset> element."""
    urls: list[str] = []
    for url_elem in root.findall(f"{{{_SITEMAP_NS}}}url"):
        loc = url_elem.findtext(f"{{{_SITEMAP_NS}}}loc")
        if loc:
            urls.append(loc.strip())
    # Also try without namespace for sitemaps that omit it.
    if not urls:
        for url_elem in root.findall("url"):
            loc = url_elem.findtext("loc")
            if loc:
                urls.append(loc.strip())
    return urls


def _extract_sitemap_locs(root: ET.Element) -> list[str]:
    """Extract child sitemap <loc> URLs from a <sitemapindex> element."""
    locs: list[str] = []
    for sitemap_elem in root.findall(f"{{{_SITEMAP_NS}}}sitemap"):
        loc = sitemap_elem.findtext(f"{{{_SITEMAP_NS}}}loc")
        if loc:
            locs.append(loc.strip())
    # Also try without namespace.
    if not locs:
        for sitemap_elem in root.findall("sitemap"):
            loc = sitemap_elem.findtext("loc")
            if loc:
                locs.append(loc.strip())
    return locs


def _is_sitemap_index(root: ET.Element) -> bool:
    """Return True if the root element is a sitemapindex."""
    tag = root.tag
    return tag == f"{{{_SITEMAP_NS}}}sitemapindex" or tag == "sitemapindex"


async def parse_sitemap(url: str) -> list[str]:
    """Discover page URLs from a site's sitemap.xml.

    Fetches ``{url}/sitemap.xml``, parses the XML, recursively resolves
    sitemap index files, deduplicates and normalizes URLs (stripping query
    strings and fragments), and returns the flat list.

    Args:
        url: Base URL of the site (e.g. ``https://example.com``).

    Returns:
        Deduplicated list of page URLs found in the sitemap.

    Raises:
        SitemapError: On 404, malformed XML, network timeout, or zero URLs.
    """
    sitemap_url = f"{url.rstrip('/')}/sitemap.xml"
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        await _process_sitemap(client, sitemap_url, seen)

    if not seen:
        raise SitemapError(f"No URLs found in sitemap at {sitemap_url}")

    return sorted(seen)


async def _process_sitemap(
    client: httpx.AsyncClient, url: str, seen: set[str]
) -> None:
    """Recursively process a sitemap or sitemap index, adding URLs to *seen*."""
    root = await _fetch_xml(client, url)

    if _is_sitemap_index(root):
        child_locs = _extract_sitemap_locs(root)
        for child_url in child_locs:
            try:
                await _process_sitemap(client, child_url, seen)
            except SitemapError:
                # Child sitemap failures are tolerated; continue with others.
                pass
    else:
        raw_urls = _extract_urls_from_urlset(root)
        for raw in raw_urls:
            normalized = _normalize_url(raw)
            if normalized:
                seen.add(normalized)
