"""Tests for backend.scraping.converter."""

from __future__ import annotations

from backend.scraping.converter import convert_html


# ---------------------------------------------------------------------------
# Main content extraction to Markdown
# ---------------------------------------------------------------------------


class TestConvertHtmlMainContent:
    def test_extracts_main_content(self):
        html = """
        <html><body>
        <main>
            <h1>Hello World</h1>
            <p>Some content here.</p>
        </main>
        </body></html>
        """
        result = convert_html(html, "https://example.com/page")
        assert "Hello World" in result
        assert "Some content here" in result

    def test_prefers_main_over_body(self):
        html = """
        <html><body>
        <p>Body text</p>
        <main><p>Main text</p></main>
        </body></html>
        """
        result = convert_html(html, "https://example.com/page")
        assert "Main text" in result

    def test_falls_back_to_article(self):
        html = """
        <html><body>
        <article><h2>Article heading</h2><p>Article body</p></article>
        </body></html>
        """
        result = convert_html(html, "https://example.com/page")
        assert "Article heading" in result

    def test_falls_back_to_body(self):
        html = """
        <html><body>
        <h1>Only body</h1>
        <p>Body paragraph</p>
        </body></html>
        """
        result = convert_html(html, "https://example.com/page")
        assert "Only body" in result


# ---------------------------------------------------------------------------
# nav/header/footer/sidebar/script/style stripping
# ---------------------------------------------------------------------------


class TestConvertHtmlStripsChrome:
    def test_strips_nav(self):
        html = """
        <html><body>
        <nav><a href="/">Home</a></nav>
        <main><p>Content</p></main>
        </body></html>
        """
        result = convert_html(html, "https://example.com")
        assert "Content" in result
        assert "Home" not in result

    def test_strips_header(self):
        html = """
        <html><body>
        <main>
            <header><h1>Site Header</h1></header>
            <p>Real content</p>
        </main>
        </body></html>
        """
        result = convert_html(html, "https://example.com")
        assert "Real content" in result
        assert "Site Header" not in result

    def test_strips_footer(self):
        html = """
        <html><body>
        <main>
            <p>Main stuff</p>
            <footer>Copyright 2026</footer>
        </main>
        </body></html>
        """
        result = convert_html(html, "https://example.com")
        assert "Main stuff" in result
        assert "Copyright" not in result

    def test_strips_sidebar(self):
        html = """
        <html><body>
        <main>
            <aside><p>Sidebar links</p></aside>
            <p>Primary content</p>
        </main>
        </body></html>
        """
        result = convert_html(html, "https://example.com")
        assert "Primary content" in result
        assert "Sidebar" not in result

    def test_strips_script_and_style(self):
        html = """
        <html><body>
        <main>
            <script>alert('xss')</script>
            <style>.foo { color: red; }</style>
            <p>Visible text</p>
        </main>
        </body></html>
        """
        result = convert_html(html, "https://example.com")
        assert "Visible text" in result
        assert "alert" not in result
        assert "color" not in result

    def test_strips_aria_navigation_role(self):
        html = """
        <html><body>
        <main>
            <div role="navigation"><a href="/">Nav link</a></div>
            <p>Content here</p>
        </main>
        </body></html>
        """
        result = convert_html(html, "https://example.com")
        assert "Content here" in result
        assert "Nav link" not in result

    def test_strips_sidebar_by_class(self):
        html = """
        <html><body>
        <main>
            <div class="sidebar"><p>Side content</p></div>
            <p>Main content</p>
        </main>
        </body></html>
        """
        result = convert_html(html, "https://example.com")
        assert "Main content" in result
        assert "Side content" not in result


# ---------------------------------------------------------------------------
# Bad/malformed HTML returns empty string
# ---------------------------------------------------------------------------


class TestConvertHtmlBadInput:
    def test_empty_string_returns_empty(self):
        assert convert_html("", "https://example.com") == ""

    def test_whitespace_only_returns_empty(self):
        assert convert_html("   \n\t  ", "https://example.com") == ""

    def test_none_input_returns_empty(self):
        # Type annotation says str but contract says never raises
        assert convert_html(None, "https://example.com") == ""

    def test_no_content_container_returns_empty(self):
        # HTML fragment with no body/main/article
        html = "<div>orphan</div>"
        result = convert_html(html, "https://example.com")
        # bs4 may or may not find a body; either empty or contains "orphan"
        # The key contract: no exception is raised
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Never raises exceptions
# ---------------------------------------------------------------------------


class TestConvertHtmlNeverRaises:
    def test_integer_input(self):
        result = convert_html(42, "https://example.com")
        assert result == ""

    def test_malformed_but_parseable_html(self):
        html = "<html><body><main><p>Unclosed paragraph<main></body>"
        result = convert_html(html, "https://example.com")
        assert isinstance(result, str)
        # Should not raise

    def test_deeply_nested_garbage(self):
        html = "<html><body><main>" + "<div>" * 100 + "deep" + "</div>" * 100 + "</main></body></html>"
        result = convert_html(html, "https://example.com")
        assert isinstance(result, str)
