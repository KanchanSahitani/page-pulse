"""
auditor.py — Core HTML auditing logic for Page Pulse.

This module is intentionally decoupled from the web framework so it can be
tested in isolation. Every public function accepts plain Python types and
returns plain Python types.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AuditReport:
    """Structured result of a single page audit."""

    url: str
    http_status: int
    response_time_ms: float
    page_title: Optional[str]
    meta_description: Optional[str]
    h1_count: int
    images_missing_alt: list[str] = field(default_factory=list)
    images_missing_alt_count: int = 0
    word_count: int = 0
    is_html: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuditError:
    """Structured error returned when the audit cannot complete."""

    error: str
    detail: str
    url: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def validate_url(raw_url: str) -> str:
    """
    Validate and normalise the incoming URL.

    Raises ValueError with a human-readable message when the URL is
    malformed or uses an unsupported scheme.
    """
    raw_url = raw_url.strip()
    if not raw_url:
        raise ValueError("URL must not be empty.")

    # Check for an explicit unsupported scheme BEFORE auto-prefixing
    if "://" in raw_url:
        scheme = raw_url.split("://", 1)[0].lower()
        if scheme not in ("http", "https"):
            raise ValueError(f"Unsupported scheme '{scheme}'. Use http or https.")
    else:
        # Allow users to omit the scheme — default to https
        raw_url = "https://" + raw_url

    parsed = urlparse(raw_url)
    if not parsed.netloc or "." not in parsed.netloc:
        raise ValueError(f"'{raw_url}' does not look like a valid URL.")

    return raw_url


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def extract_title(soup: BeautifulSoup) -> Optional[str]:
    """Return the <title> text, or None."""
    tag = soup.find("title")
    return tag.get_text(strip=True) if tag else None


def extract_meta_description(soup: BeautifulSoup) -> Optional[str]:
    """Return the content of <meta name='description'>, or None."""
    tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def count_h1(soup: BeautifulSoup) -> int:
    """Count the number of <h1> tags."""
    return len(soup.find_all("h1"))


def find_images_missing_alt(soup: BeautifulSoup) -> list[str]:
    """
    Return a list of <img> src values where the alt attribute is missing
    or empty.
    """
    missing: list[str] = []
    for img in soup.find_all("img"):
        alt = img.get("alt")
        if alt is None or alt.strip() == "":
            src = img.get("src", "(no src)")
            missing.append(src)
    return missing


def estimate_word_count(soup: BeautifulSoup) -> int:
    """
    Approximate the visible word count by stripping <script> and <style>
    elements, then splitting the remaining text on whitespace.
    """
    # Work on a copy so we don't mutate the caller's soup
    clone = BeautifulSoup(str(soup), "lxml")
    for tag in clone(["script", "style", "noscript"]):
        tag.decompose()
    text = clone.get_text(separator=" ", strip=True)
    words = text.split()
    return len(words)


def parse_html(html: str) -> dict:
    """
    Parse raw HTML and return a dict with all extracted metrics.

    This is the single entry-point used by the audit endpoint and by tests.
    """
    soup = BeautifulSoup(html, "lxml")

    imgs_missing = find_images_missing_alt(soup)

    return {
        "page_title": extract_title(soup),
        "meta_description": extract_meta_description(soup),
        "h1_count": count_h1(soup),
        "images_missing_alt": imgs_missing,
        "images_missing_alt_count": len(imgs_missing),
        "word_count": estimate_word_count(soup),
    }


# ---------------------------------------------------------------------------
# Full audit (fetch + parse)
# ---------------------------------------------------------------------------

_TIMEOUT = 15.0  # seconds

async def audit_url(raw_url: str) -> AuditReport | AuditError:
    """
    Perform a full audit: validate → fetch → parse → return report.

    Returns an AuditReport on success or an AuditError on failure.
    """
    # 1. Validate
    try:
        url = validate_url(raw_url)
    except ValueError as exc:
        return AuditError(
            error="invalid_url",
            detail=str(exc),
            url=raw_url,
        )

    # 2. Fetch
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(_TIMEOUT),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Upgrade-Insecure-Requests": "1",
            },
        ) as client:
            start = time.perf_counter()
            response = await client.get(url)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    except httpx.TimeoutException:
        return AuditError(
            error="timeout",
            detail=f"The request to '{url}' timed out after {_TIMEOUT}s.",
            url=url,
        )
    except httpx.ConnectError:
        return AuditError(
            error="connection_error",
            detail=f"Could not connect to '{url}'. Check the domain name.",
            url=url,
        )
    except httpx.RequestError as exc:
        return AuditError(
            error="request_error",
            detail=str(exc),
            url=url,
        )

    # 3. Content-type check
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type.lower():
        return AuditError(
            error="not_html",
            detail=(
                f"The response Content-Type is '{content_type}', "
                "which is not HTML. Page Pulse only audits HTML pages."
            ),
            url=url,
        )

    # 4. Parse
    metrics = parse_html(response.text)

    return AuditReport(
        url=url,
        http_status=response.status_code,
        response_time_ms=elapsed_ms,
        is_html=True,
        **metrics,
    )
