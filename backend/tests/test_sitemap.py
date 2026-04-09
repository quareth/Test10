"""Tests for backend.scraping.sitemap."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from xml.sax.saxutils import escape as xml_escape

from backend.scraping.sitemap import SitemapError, parse_sitemap


def _run(coro):
    """Run an async coroutine."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _urlset_xml(urls: list[str]) -> bytes:
    """Build a valid <urlset> sitemap XML."""
    entries = "\n".join(
        f"<url><loc>{xml_escape(u)}</loc></url>" for u in urls
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="{_NS}">{entries}</urlset>'
    ).encode()


def _index_xml(sitemap_urls: list[str]) -> bytes:
    """Build a valid <sitemapindex> XML."""
    entries = "\n".join(
        f"<sitemap><loc>{u}</loc></sitemap>" for u in sitemap_urls
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<sitemapindex xmlns="{_NS}">{entries}</sitemapindex>'
    ).encode()


def _mock_response(status_code: int = 200, content: bytes = b"") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    return resp


# ---------------------------------------------------------------------------
# Valid sitemap parsing returning URL list
# ---------------------------------------------------------------------------


class TestParseSitemapValid:
    def test_returns_url_list(self):
        xml = _urlset_xml([
            "https://example.com/a",
            "https://example.com/b",
        ])
        resp = _mock_response(200, xml)

        async def fake_get(url, **kwargs):
            return resp

        with patch("backend.scraping.sitemap.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = _run(parse_sitemap("https://example.com"))

        assert "https://example.com/a" in result
        assert "https://example.com/b" in result
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Sitemap index with nested sitemaps (recursive)
# ---------------------------------------------------------------------------


class TestParseSitemapIndex:
    def test_recursive_index(self):
        index = _index_xml([
            "https://example.com/sitemap-pages.xml",
            "https://example.com/sitemap-blog.xml",
        ])
        pages_xml = _urlset_xml(["https://example.com/page1"])
        blog_xml = _urlset_xml(["https://example.com/blog1"])

        responses = {
            "https://example.com/sitemap.xml": _mock_response(200, index),
            "https://example.com/sitemap-pages.xml": _mock_response(200, pages_xml),
            "https://example.com/sitemap-blog.xml": _mock_response(200, blog_xml),
        }

        async def fake_get(url, **kwargs):
            return responses[url]

        with patch("backend.scraping.sitemap.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = _run(parse_sitemap("https://example.com"))

        assert "https://example.com/page1" in result
        assert "https://example.com/blog1" in result
        assert len(result) == 2


# ---------------------------------------------------------------------------
# 404 raises SitemapError
# ---------------------------------------------------------------------------


class TestParseSitemap404:
    def test_404_raises(self):
        resp = _mock_response(404, b"Not Found")

        async def fake_get(url, **kwargs):
            return resp

        with patch("backend.scraping.sitemap.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            with pytest.raises(SitemapError, match="not found"):
                _run(parse_sitemap("https://example.com"))


# ---------------------------------------------------------------------------
# Malformed XML raises SitemapError
# ---------------------------------------------------------------------------


class TestParseSitemapMalformedXML:
    def test_malformed_xml_raises(self):
        resp = _mock_response(200, b"<not-valid-xml>>>>>")

        async def fake_get(url, **kwargs):
            return resp

        with patch("backend.scraping.sitemap.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            with pytest.raises(SitemapError, match="parse"):
                _run(parse_sitemap("https://example.com"))


# ---------------------------------------------------------------------------
# Network timeout raises SitemapError
# ---------------------------------------------------------------------------


class TestParseSitemapTimeout:
    def test_timeout_raises(self):
        async def fake_get(url, **kwargs):
            raise httpx.ReadTimeout("timed out")

        with patch("backend.scraping.sitemap.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            with pytest.raises(SitemapError, match="[Tt]imeout"):
                _run(parse_sitemap("https://example.com"))


# ---------------------------------------------------------------------------
# URL deduplication
# ---------------------------------------------------------------------------


class TestParseSitemapDedup:
    def test_duplicate_urls_deduplicated(self):
        xml = _urlset_xml([
            "https://example.com/page",
            "https://example.com/page",
            "https://example.com/page",
        ])
        resp = _mock_response(200, xml)

        async def fake_get(url, **kwargs):
            return resp

        with patch("backend.scraping.sitemap.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = _run(parse_sitemap("https://example.com"))

        assert len(result) == 1
        assert result[0] == "https://example.com/page"


# ---------------------------------------------------------------------------
# Query string and fragment stripping
# ---------------------------------------------------------------------------


class TestParseSitemapNormalization:
    def test_query_and_fragment_stripped(self):
        xml = _urlset_xml([
            "https://example.com/page?utm_source=test",
            "https://example.com/page#section",
            "https://example.com/other?a=1&b=2#frag",
        ])
        resp = _mock_response(200, xml)

        async def fake_get(url, **kwargs):
            return resp

        with patch("backend.scraping.sitemap.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = fake_get
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = _run(parse_sitemap("https://example.com"))

        # page?... and page#... should both normalize to /page -> deduplicated
        assert "https://example.com/page" in result
        assert "https://example.com/other" in result
        # No query strings or fragments in the output
        for url in result:
            assert "?" not in url
            assert "#" not in url
