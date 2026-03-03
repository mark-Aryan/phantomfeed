"""
pipeline/normalizer.py
======================
Normalizes raw feed items from all sources into a canonical dict:

{
  "title":        str,
  "description":  str,
  "url":          str,
  "published_at": str (ISO-8601),
  "source":       str,
  "raw":          dict (original),
}
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


def _clean_html(text: str) -> str:
    """Strip HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(raw: str) -> str:
    """Try multiple date formats, return ISO-8601 UTC string."""
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


def normalize_newsapi(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a NewsAPI article object."""
    return {
        "title": _clean_html(item.get("title") or ""),
        "description": _clean_html(item.get("description") or item.get("content") or ""),
        "url": item.get("url", ""),
        "published_at": _parse_date(item.get("publishedAt", "")),
        "source": item.get("source", {}).get("name", "newsapi"),
        "raw": item,
    }


def normalize_nvd(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize an NVD CVE item."""
    cve_id = item.get("id", "")
    desc_list = (
        item.get("descriptions", [])
        or item.get("cve", {}).get("description", {}).get("description_data", [])
    )
    desc = next(
        (d.get("value", "") for d in desc_list if d.get("lang") == "en"),
        "",
    )
    published = item.get("published", "") or item.get("publishedDate", "")
    refs = item.get("references", [])
    ref_url = refs[0].get("url", "") if refs else ""
    url = ref_url or f"https://nvd.nist.gov/vuln/detail/{cve_id}"
    return {
        "title": cve_id if cve_id else "NVD Advisory",
        "description": _clean_html(desc),
        "url": url,
        "published_at": _parse_date(published),
        "source": "NVD",
        "raw": item,
    }


def normalize_rss(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a feedparser RSS entry dict."""
    title = _clean_html(item.get("title", ""))
    summary = _clean_html(
        item.get("summary", "") or item.get("description", "")
    )
    link = item.get("link", "")
    pub = item.get("published", "") or item.get("updated", "")
    source = item.get("_feed_name", "rss")
    return {
        "title": title,
        "description": summary,
        "url": link,
        "published_at": _parse_date(pub),
        "source": source,
        "raw": item,
    }


def normalize(item: dict[str, Any], fmt: str = "rss") -> dict[str, Any]:
    """Dispatch to the right normalizer by format string."""
    if fmt == "newsapi":
        return normalize_newsapi(item)
    elif fmt == "nvd":
        return normalize_nvd(item)
    else:
        return normalize_rss(item)
