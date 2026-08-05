"""
test_auditor.py — Unit tests for the Page Pulse auditing logic.

Covers:
  - Happy-path parsing of a realistic HTML page.
  - Failure: invalid / empty URL.
  - Failure: timeout during fetch.
  - Failure: non-HTML content type.
  - Edge cases for individual parsing helpers.
"""

from __future__ import annotations

import pytest
import httpx
import respx

from backend.auditor import (
    validate_url,
    parse_html,
    extract_title,
    extract_meta_description,
    count_h1,
    find_images_missing_alt,
    estimate_word_count,
    audit_url,
    AuditReport,
    AuditError,
)
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Fixtures — realistic HTML snippets
# ---------------------------------------------------------------------------

SAMPLE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Example Domain</title>
  <meta name="description" content="This is a sample page for testing purposes.">
</head>
<body>
  <h1>Welcome to Example</h1>
  <p>This is a paragraph with some words for word count testing.</p>
  <p>Another paragraph here with more content to count.</p>
  <img src="/logo.png" alt="Logo" />
  <img src="/hero.jpg" />
  <img src="/banner.webp" alt="" />
  <script>var x = 1;</script>
  <style>body { margin: 0; }</style>
</body>
</html>
"""

MINIMAL_HTML = """\
<!DOCTYPE html>
<html><head><title></title></head><body></body></html>
"""


# ---------------------------------------------------------------------------
# Unit tests: URL validation
# ---------------------------------------------------------------------------

class TestValidateUrl:
    def test_valid_https(self):
        assert validate_url("https://example.com") == "https://example.com"

    def test_valid_http(self):
        assert validate_url("http://example.com") == "http://example.com"

    def test_auto_prefix_https(self):
        """Users often omit the scheme — we should prepend https://."""
        assert validate_url("example.com") == "https://example.com"

    def test_strips_whitespace(self):
        assert validate_url("  https://example.com  ") == "https://example.com"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_url("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_url("   ")

    def test_invalid_domain_raises(self):
        with pytest.raises(ValueError, match="does not look like a valid URL"):
            validate_url("not-a-url")

    def test_ftp_scheme_raises(self):
        with pytest.raises(ValueError, match="Unsupported scheme"):
            validate_url("ftp://files.example.com/data")


# ---------------------------------------------------------------------------
# Unit tests: HTML parsing helpers
# ---------------------------------------------------------------------------

class TestExtractTitle:
    def test_normal_title(self):
        soup = BeautifulSoup(SAMPLE_HTML, "lxml")
        assert extract_title(soup) == "Example Domain"

    def test_missing_title(self):
        soup = BeautifulSoup("<html><head></head><body></body></html>", "lxml")
        assert extract_title(soup) is None

    def test_empty_title(self):
        soup = BeautifulSoup(MINIMAL_HTML, "lxml")
        assert extract_title(soup) == ""


class TestExtractMetaDescription:
    def test_normal_description(self):
        soup = BeautifulSoup(SAMPLE_HTML, "lxml")
        assert extract_meta_description(soup) == "This is a sample page for testing purposes."

    def test_missing_description(self):
        soup = BeautifulSoup("<html><head></head><body></body></html>", "lxml")
        assert extract_meta_description(soup) is None

    def test_case_insensitive(self):
        html = '<html><head><meta name="Description" content="Mixed case"></head><body></body></html>'
        soup = BeautifulSoup(html, "lxml")
        assert extract_meta_description(soup) == "Mixed case"


class TestCountH1:
    def test_single_h1(self):
        soup = BeautifulSoup(SAMPLE_HTML, "lxml")
        assert count_h1(soup) == 1

    def test_multiple_h1(self):
        html = "<html><body><h1>A</h1><h1>B</h1><h1>C</h1></body></html>"
        soup = BeautifulSoup(html, "lxml")
        assert count_h1(soup) == 3

    def test_no_h1(self):
        html = "<html><body><h2>No H1 here</h2></body></html>"
        soup = BeautifulSoup(html, "lxml")
        assert count_h1(soup) == 0


class TestFindImagesMissingAlt:
    def test_sample_html(self):
        """SAMPLE_HTML has 2 images without (meaningful) alt: hero.jpg and banner.webp."""
        soup = BeautifulSoup(SAMPLE_HTML, "lxml")
        missing = find_images_missing_alt(soup)
        assert len(missing) == 2
        assert "/hero.jpg" in missing
        assert "/banner.webp" in missing

    def test_all_images_have_alt(self):
        html = '<html><body><img src="a.png" alt="A"><img src="b.png" alt="B"></body></html>'
        soup = BeautifulSoup(html, "lxml")
        assert find_images_missing_alt(soup) == []

    def test_no_images(self):
        soup = BeautifulSoup("<html><body><p>No images</p></body></html>", "lxml")
        assert find_images_missing_alt(soup) == []


class TestEstimateWordCount:
    def test_excludes_script_and_style(self):
        soup = BeautifulSoup(SAMPLE_HTML, "lxml")
        wc = estimate_word_count(soup)
        # The visible text has roughly 20-30 words; script/style must NOT be counted.
        assert wc > 10
        assert wc < 50  # sanity upper bound

    def test_empty_body(self):
        soup = BeautifulSoup(MINIMAL_HTML, "lxml")
        assert estimate_word_count(soup) == 0


# ---------------------------------------------------------------------------
# Unit tests: parse_html (integration of helpers)
# ---------------------------------------------------------------------------

class TestParseHtml:
    def test_returns_all_fields(self):
        result = parse_html(SAMPLE_HTML)
        assert "page_title" in result
        assert "meta_description" in result
        assert "h1_count" in result
        assert "images_missing_alt" in result
        assert "images_missing_alt_count" in result
        assert "word_count" in result

    def test_correct_values(self):
        result = parse_html(SAMPLE_HTML)
        assert result["page_title"] == "Example Domain"
        assert result["meta_description"] == "This is a sample page for testing purposes."
        assert result["h1_count"] == 1
        assert result["images_missing_alt_count"] == 2
        assert result["word_count"] > 0


# ---------------------------------------------------------------------------
# Async tests: full audit_url flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAuditUrl:

    @respx.mock
    async def test_happy_path(self):
        """A normal HTML page should produce an AuditReport."""
        respx.get("https://example.com/").mock(
            return_value=httpx.Response(
                200,
                text=SAMPLE_HTML,
                headers={"content-type": "text/html; charset=utf-8"},
            )
        )
        result = await audit_url("https://example.com")
        assert isinstance(result, AuditReport)
        assert result.http_status == 200
        assert result.page_title == "Example Domain"
        assert result.h1_count == 1
        assert result.images_missing_alt_count == 2
        assert result.word_count > 0
        assert result.response_time_ms >= 0

    async def test_invalid_url_returns_error(self):
        """An obviously bogus URL should return AuditError without hitting the network."""
        result = await audit_url("")
        assert isinstance(result, AuditError)
        assert result.error == "invalid_url"

    @respx.mock
    async def test_timeout_returns_error(self):
        """A request that times out should produce a timeout AuditError."""
        respx.get("https://slow-site.com/").mock(side_effect=httpx.ReadTimeout("timed out"))
        result = await audit_url("https://slow-site.com")
        assert isinstance(result, AuditError)
        assert result.error == "timeout"

    @respx.mock
    async def test_non_html_returns_error(self):
        """A response with a non-HTML content type should produce a not_html AuditError."""
        respx.get("https://example.com/image.png").mock(
            return_value=httpx.Response(
                200,
                content=b"\x89PNG fake",
                headers={"content-type": "image/png"},
            )
        )
        result = await audit_url("https://example.com/image.png")
        assert isinstance(result, AuditError)
        assert result.error == "not_html"

    @respx.mock
    async def test_connection_error(self):
        """A DNS / connection failure should produce a connection_error AuditError."""
        respx.get("https://does-not-exist.invalid/").mock(
            side_effect=httpx.ConnectError("DNS resolution failed")
        )
        result = await audit_url("https://does-not-exist.invalid")
        assert isinstance(result, AuditError)
        assert result.error == "connection_error"


# ---------------------------------------------------------------------------
# FastAPI Route Tests
# ---------------------------------------------------------------------------

class TestHomePage:
    def test_home_page_returns_html(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Page Pulse" in response.text

    @respx.mock
    def test_home_page_dynamic_query_param(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        respx.get("https://example.com/").mock(
            return_value=httpx.Response(
                200,
                text=SAMPLE_HTML,
                headers={"content-type": "text/html; charset=utf-8"},
            )
        )
        client = TestClient(app)
        response = client.get("/?url=https://example.com")
        assert response.status_code == 200
        assert "Example Domain" in response.text

