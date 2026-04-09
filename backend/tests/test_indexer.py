"""Tests for backend.scraping.indexer."""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.schemas import PageContent
from backend.scraping.indexer import (
    _sanitize_segment,
    _url_path_to_fs_path,
    assemble_bulk,
    assemble_structured,
)


# --- _sanitize_segment ---


def test_sanitize_basic():
    assert _sanitize_segment("hello") == "hello"


def test_sanitize_special_chars():
    assert _sanitize_segment("foo bar!@#baz") == "foo_bar___baz"


def test_sanitize_traversal_rejected():
    assert _sanitize_segment("..") == ""


def test_sanitize_dots_stripped():
    assert _sanitize_segment("...leading") == "leading"
    assert _sanitize_segment("trailing...") == "trailing"


def test_sanitize_truncation():
    long_seg = "a" * 200
    result = _sanitize_segment(long_seg)
    assert len(result) == 100


def test_sanitize_empty_after_cleaning():
    assert _sanitize_segment("...") == ""


# --- _url_path_to_fs_path ---


def test_path_empty():
    assert _url_path_to_fs_path("") == Path("index.md")


def test_path_slash_only():
    assert _url_path_to_fs_path("/") == Path("index.md")


def test_path_trailing_slash():
    result = _url_path_to_fs_path("/docs/guide/")
    assert result == Path("docs/guide/index.md")


def test_path_no_trailing_slash():
    result = _url_path_to_fs_path("/docs/guide")
    assert result == Path("docs/guide.md")


def test_path_deep():
    result = _url_path_to_fs_path("/a/b/c/page")
    assert result == Path("a/b/c/page.md")


def test_path_traversal_filtered():
    result = _url_path_to_fs_path("/../../../etc/passwd")
    # '..' segments are dropped, rest is sanitized
    assert ".." not in str(result)


def test_path_special_chars_in_segments():
    result = _url_path_to_fs_path("/hello world/foo@bar")
    assert result == Path("hello_world/foo_bar.md")


def test_path_all_segments_empty_after_sanitize():
    result = _url_path_to_fs_path("/.../.../")
    assert result == Path("index.md")


# --- assemble_bulk ---


def test_assemble_bulk_single_page():
    pages = [
        PageContent(url="https://example.com/a", url_path="/a", markdown="# Hello")
    ]
    result = assemble_bulk(pages)
    assert "---\nSource: https://example.com/a\nScraped:" in result
    assert "---\n# Hello" in result


def test_assemble_bulk_multiple_pages():
    pages = [
        PageContent(url="https://example.com/a", url_path="/a", markdown="Page A"),
        PageContent(url="https://example.com/b", url_path="/b", markdown="Page B"),
    ]
    result = assemble_bulk(pages)
    assert result.count("Source: ") == 2
    assert "Page A" in result
    assert "Page B" in result


def test_assemble_bulk_empty_list():
    result = assemble_bulk([])
    assert result == ""


def test_assemble_bulk_frontmatter_format():
    pages = [
        PageContent(url="https://example.com/x", url_path="/x", markdown="content")
    ]
    result = assemble_bulk(pages)
    lines = result.split("\n")
    assert lines[0] == "---"
    assert lines[1].startswith("Source: https://example.com/x")
    assert lines[2].startswith("Scraped: ")
    assert lines[3] == "---"
    assert lines[4] == "content"


# --- assemble_structured ---


def test_assemble_structured_creates_files():
    pages = [
        PageContent(url="https://example.com/docs", url_path="/docs", markdown="# Docs"),
        PageContent(
            url="https://example.com/about/",
            url_path="/about/",
            markdown="# About",
        ),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        written = assemble_structured(pages, base)
        assert len(written) == 2

        # Check first file
        docs_file = base / "structured" / "docs.md"
        assert docs_file.exists()
        assert docs_file.read_text() == "# Docs"

        # Check trailing-slash produces index.md
        about_file = base / "structured" / "about" / "index.md"
        assert about_file.exists()
        assert about_file.read_text() == "# About"

        assert set(written) == {docs_file, about_file}


def test_assemble_structured_sanitizes_paths():
    pages = [
        PageContent(
            url="https://example.com/foo/../bar",
            url_path="/foo/../bar",
            markdown="content",
        )
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        written = assemble_structured(pages, base)
        assert len(written) == 1
        # '..' should be dropped, not traversed
        path_str = str(written[0])
        assert ".." not in path_str
        assert written[0].exists()


def test_assemble_structured_root_path():
    pages = [
        PageContent(url="https://example.com/", url_path="/", markdown="# Root")
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        written = assemble_structured(pages, base)
        assert len(written) == 1
        expected = base / "structured" / "index.md"
        assert written[0] == expected
        assert expected.read_text() == "# Root"


def test_assemble_structured_empty_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        written = assemble_structured([], base)
        assert written == []
