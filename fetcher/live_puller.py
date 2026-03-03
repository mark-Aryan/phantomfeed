"""
fetcher/live_puller.py
=======================
UPGRADE #2 — Live news puller.

Fetches only LIVE / recent news (within last N minutes).
Respects a "last_seen" cursor per source so repeated runs
never return old articles — true incremental streaming.

Sources supported:
  • NewsAPI  (publishedAt recency filter)
  • NVD      (pubStartDate recency filter)
  • RSS      (per-feed cursor stored in SQLite)

Cursor persistence: lightweight SQLite table 'live_cursors'
integrated into the existing DedupeDB so no extra files needed.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

# ─── Cursor DB ────────────────────────────────────────────────────────────────

CURSOR_DDL = """
CREATE TABLE IF NOT EXISTS live_cursors (
    source      TEXT PRIMARY KEY,
    last_seen   TEXT NOT NULL,    -- ISO-8601 UTC timestamp
    updated_at  TEXT NOT NULL
);
"""


class CursorStore:
    """Persists per-source high-water marks."""

    def __init__(self, db_path: str | Path = "data/dedupe.db") -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(CURSOR_DDL)
        self._conn.commit()

    def get(self, source: str, default_minutes_back: int = 60) -> datetime:
        row = self._conn.execute(
            "SELECT last_seen FROM live_cursors WHERE source = ?", (source,)
        ).fetchone()
        if row:
            try:
                return datetime.fromisoformat(row[0])
            except ValueError:
                pass
        # First run: look back default_minutes_back
        return datetime.now(timezone.utc) - timedelta(minutes=default_minutes_back)

    def update(self, source: str, ts: datetime) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO live_cursors (source, last_seen, updated_at)
               VALUES (?,?,?)
               ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen,
                                                  updated_at=excluded.updated_at""",
            (source, ts.isoformat(), now),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ─── Recency filter ────────────────────────────────────────────────────────────

def _parse_dt(raw: str) -> datetime | None:
    """Parse any date string to timezone-aware UTC datetime."""
    from email.utils import parsedate_to_datetime
    if not raw:
        return None
    # RFC 2822
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
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
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def _is_live(raw_date: str, since: datetime) -> bool:
    dt = _parse_dt(raw_date)
    if dt is None:
        return True   # can't determine — include to be safe
    return dt > since


# ─── NewsAPI live fetch ────────────────────────────────────────────────────────

async def fetch_newsapi_live(
    api_key: str,
    cursor: CursorStore,
    query: str = "cybersecurity OR CVE OR ransomware OR vulnerability",
    page_size: int = 20,
    session: aiohttp.ClientSession | None = None,
    lookback_minutes: int = 90,
) -> list[dict]:
    """Fetch only articles newer than cursor['newsapi']."""
    since = cursor.get("newsapi", lookback_minutes)
    from_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "q":        query,
        "from":     from_str,
        "sortBy":   "publishedAt",
        "pageSize": page_size,
        "language": "en",
        "apiKey":   api_key,
    }

    url = "https://newsapi.org/v2/everything"
    close_after = session is None
    if session is None:
        session = aiohttp.ClientSession()

    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json()
                articles = data.get("articles", [])
                # Filter strictly newer than cursor
                fresh = [a for a in articles if _is_live(a.get("publishedAt", ""), since)]
                # Update cursor to newest seen
                if fresh:
                    newest = max(
                        (_parse_dt(a.get("publishedAt", "")) for a in fresh),
                        default=since,
                    )
                    if newest and newest > since:
                        cursor.update("newsapi", newest)
                log.info("[NewsAPI-Live] %d fresh articles (since %s)", len(fresh), from_str)
                return fresh
            else:
                log.warning("[NewsAPI-Live] HTTP %d", resp.status)
                return []
    except Exception as exc:
        log.error("[NewsAPI-Live] Error: %s", exc)
        return []
    finally:
        if close_after:
            await session.close()


# ─── NVD live fetch ───────────────────────────────────────────────────────────

async def fetch_nvd_live(
    cursor: CursorStore,
    api_key: str = "",
    lookback_minutes: int = 120,
    session: aiohttp.ClientSession | None = None,
    min_cvss: float = 0.0,
) -> list[dict]:
    """Fetch CVEs published/modified since cursor['nvd']."""
    since = cursor.get("nvd", lookback_minutes)
    start = since.strftime("%Y-%m-%dT%H:%M:%S.000")
    end   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.999")

    params: dict[str, Any] = {
        "pubStartDate": start,
        "pubEndDate":   end,
        "resultsPerPage": 50,
    }
    headers: dict[str, str] = {}
    if api_key:
        headers["apiKey"] = api_key

    close_after = session is None
    if session is None:
        session = aiohttp.ClientSession()

    try:
        async with session.get(
            "https://services.nvd.nist.gov/rest/json/cves/2.0",
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                vulns = data.get("vulnerabilities", [])
                items = []
                for v in vulns:
                    cve = v.get("cve", {})
                    if min_cvss > 0:
                        score = 0.0
                        for m in cve.get("metrics", {}).get("cvssMetricV31", []):
                            score = max(score, m.get("cvssData", {}).get("baseScore", 0))
                        if score < min_cvss:
                            continue
                    items.append(v)
                # Update cursor
                if items:
                    newest = datetime.now(timezone.utc)
                    cursor.update("nvd", newest)
                log.info("[NVD-Live] %d fresh CVEs (since %s)", len(items), start)
                return items
            else:
                log.warning("[NVD-Live] HTTP %d", resp.status)
                return []
    except Exception as exc:
        log.error("[NVD-Live] Error: %s", exc)
        return []
    finally:
        if close_after:
            await session.close()


# ─── RSS live fetch ────────────────────────────────────────────────────────────

async def fetch_rss_live(
    feeds: list[dict],
    cursor: CursorStore,
    lookback_minutes: int = 90,
    session: aiohttp.ClientSession | None = None,
) -> list[dict]:
    """Fetch RSS entries newer than per-feed cursors."""
    import feedparser

    close_after = session is None
    if session is None:
        session = aiohttp.ClientSession()

    all_fresh: list[dict] = []
    try:
        tasks = [
            _fetch_one_feed(feed, cursor, lookback_minutes, session)
            for feed in feeds
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for feed, result in zip(feeds, results):
            if isinstance(result, Exception):
                log.warning("[RSS-Live] Feed %s error: %s", feed.get("name"), result)
            else:
                all_fresh.extend(result)
    finally:
        if close_after:
            await session.close()

    return all_fresh


async def _fetch_one_feed(
    feed: dict,
    cursor: CursorStore,
    lookback_minutes: int,
    session: aiohttp.ClientSession,
) -> list[dict]:
    import feedparser

    feed_url  = feed.get("url", "")
    feed_name = feed.get("name", feed_url)
    cursor_key = f"rss:{hashlib.md5(feed_url.encode()).hexdigest()[:8]}"
    since = cursor.get(cursor_key, lookback_minutes)

    try:
        async with session.get(
            feed_url,
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"User-Agent": "PhantomFeed/1.0 (+https://codexploit.in)"},
        ) as resp:
            text = await resp.text()
    except Exception as exc:
        log.warning("[RSS-Live] Could not fetch %s: %s", feed_url, exc)
        return []

    parsed = feedparser.parse(text)
    fresh = []
    newest_dt = since

    for entry in parsed.entries:
        pub = entry.get("published", "") or entry.get("updated", "")
        if not _is_live(pub, since):
            continue
        entry["_feed_name"] = feed_name
        fresh.append(dict(entry))
        dt = _parse_dt(pub)
        if dt and dt > newest_dt:
            newest_dt = dt

    if fresh and newest_dt > since:
        cursor.update(cursor_key, newest_dt)

    log.info("[RSS-Live] %s → %d fresh entries", feed_name, len(fresh))
    return fresh


# ─── Combined live pull ────────────────────────────────────────────────────────

async def pull_live(config: dict[str, Any], cursor: CursorStore) -> dict[str, list[dict]]:
    """
    Pull live items from all configured sources.

    Returns: {"newsapi": [...], "nvd": [...], "rss": [...]}
    """
    lookback = int(config.get("live_lookback_minutes", 90))
    results: dict[str, list[dict]] = {"newsapi": [], "nvd": [], "rss": []}

    async with aiohttp.ClientSession() as session:
        tasks = []

        if config.get("newsapi_key"):
            tasks.append(("newsapi", fetch_newsapi_live(
                api_key=config["newsapi_key"],
                cursor=cursor,
                query=config.get("newsapi_query", "cybersecurity OR CVE OR ransomware OR vulnerability"),
                page_size=config.get("newsapi_page_size", 20),
                session=session,
                lookback_minutes=lookback,
            )))

        if config.get("nvd_enabled", True):
            tasks.append(("nvd", fetch_nvd_live(
                cursor=cursor,
                api_key=config.get("nvd_api_key", ""),
                lookback_minutes=lookback,
                session=session,
                min_cvss=float(config.get("nvd_min_cvss", 0.0)),
            )))

        if config.get("rss_enabled", True):
            from fetcher.rss_fetcher import DEFAULT_FEEDS
            feeds = config.get("rss_feeds") or DEFAULT_FEEDS
            tasks.append(("rss", fetch_rss_live(
                feeds=feeds,
                cursor=cursor,
                lookback_minutes=lookback,
                session=session,
            )))

        gathered = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        for (fmt, _), res in zip(tasks, gathered):
            if isinstance(res, Exception):
                log.error("[LivePull] Source %s failed: %s", fmt, res)
            else:
                results[fmt] = res

    total = sum(len(v) for v in results.values())
    log.info("[LivePull] Total live items fetched: %d", total)
    return results
