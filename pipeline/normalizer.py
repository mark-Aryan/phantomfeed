# =============================================================================
# pipeline/normalizer.py — PhantomFeed v2
# =============================================================================
# Copyright (c) 2026 Aryan Kumar Upadhyay (@aryankrupadhyay)
# Brand: codeXploit · https://codexploit.in
# License: MIT — Retain this header and brand attribution in all copies.
#
# FIXES IN THIS VERSION
# ─────────────────────
# FIX-1  normalize_nvd() now correctly handles BOTH input shapes:
#        (a) raw vulnerability wrapper  {"cve": {...}, "id": "CVE-..."}
#            as returned by nvd_fetcher.fetch() before _fetcher injection
#        (b) pre-extracted inner CVE dict {"id": "CVE-...", "descriptions": [...]}
#            as returned by nvd_fetcher.fetch() after the inner loop
#        The previous version assumed shape (b) only but nvd_fetcher.fetch()
#        injects _fetcher on the inner cve dict and returns that — so shape (b)
#        was correct. However live_puller.fetch_nvd_live() returns shape (a).
#        This version handles both transparently.
# FIX-2  normalize_rss() falls back to entry.get("content") for items
#        that use content:encoded instead of summary/description.
# FIX-3  All normalizers now guarantee non-empty 'title' (no silent empty str).
# =============================================================================

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


# ── Text cleaning ──────────────────────────────────────────────────────────────

def _clean_html(text: str) -> str:
    """Strip HTML tags and decode entities. Returns clean plain text."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(raw: str) -> str:
    """Try multiple date formats; return ISO-8601 UTC string."""
    if not raw:
        return datetime.now(timezone.utc).isoformat()

    # RFC 2822 (RSS feeds)
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        pass

    # ISO-8601 variants
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.000",   # NVD live format
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue

    return raw  # return as-is if nothing worked


# ── Per-source normalizers ─────────────────────────────────────────────────────

def normalize_newsapi(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a NewsAPI article object."""
    title = _clean_html(item.get("title") or "")
    return {
        "title":        title or "Untitled Article",
        "description":  _clean_html(item.get("description") or item.get("content") or ""),
        "url":          item.get("url", ""),
        "published_at": _parse_date(item.get("publishedAt", "")),
        "source":       item.get("source", {}).get("name", "newsapi"),
        "raw":          item,
    }


def normalize_nvd(item: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize an NVD item.

    FIX-1: Handles both shapes:
      Shape A (live_puller): {"cve": {"id": ..., "descriptions": [...], ...}}
      Shape B (nvd_fetcher):  {"id": ..., "descriptions": [...], "_fetcher": "nvd"}
    """
    # Detect shape A (wrapper with nested "cve" key)
    if "cve" in item and isinstance(item["cve"], dict):
        cve_data = item["cve"]
    else:
        cve_data = item

    cve_id = cve_data.get("id", "")

    # Description — NVD 2.0 uses "descriptions" list with lang codes
    desc_list = cve_data.get("descriptions", [])
    # Fallback: older NVD 1.0 structure
    if not desc_list:
        desc_list = (
            cve_data.get("cve", {})
            .get("description", {})
            .get("description_data", [])
        )
    desc = next(
        (d.get("value", "") for d in desc_list if d.get("lang") == "en"),
        "",
    )

    # Publication date
    published = cve_data.get("published", "") or cve_data.get("publishedDate", "")

    # Reference URL
    refs    = cve_data.get("references", [])
    ref_url = refs[0].get("url", "") if refs else ""
    url     = ref_url or f"https://nvd.nist.gov/vuln/detail/{cve_id}"

    return {
        "title":        cve_id if cve_id else "NVD Advisory",
        "description":  _clean_html(desc),
        "url":          url,
        "published_at": _parse_date(published),
        "source":       "NVD",
        "raw":          item,
    }


def normalize_rss(item: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a feedparser RSS entry dict.

    FIX-2: Falls back to content:encoded field for feeds that don't use summary.
    """
    title   = _clean_html(item.get("title", ""))
    # Try summary → description → content (content:encoded)
    summary = (
        item.get("summary", "")
        or item.get("description", "")
        or _extract_content(item)
    )
    pub    = item.get("published", "") or item.get("updated", "")
    source = item.get("_feed_name", "rss")

    return {
        "title":        title or "Untitled",
        "description":  _clean_html(summary),
        "url":          item.get("link", ""),
        "published_at": _parse_date(pub),
        "source":       source,
        "raw":          item,
    }


def _extract_content(item: dict[str, Any]) -> str:
    """Extract text from content:encoded or content[] fields."""
    # feedparser puts content:encoded in item.content as a list of dicts
    content_list = item.get("content", [])
    if content_list and isinstance(content_list, list):
        return content_list[0].get("value", "")
    return ""


def normalize(item: dict[str, Any], fmt: str = "rss") -> dict[str, Any]:
    """
    Dispatch to the correct normalizer by format string.

    fmt: "newsapi" | "nvd" | "rss" (default)
    """
    if fmt == "newsapi":
        return normalize_newsapi(item)
    elif fmt == "nvd":
        return normalize_nvd(item)
    else:
        return normalize_rss(item)
