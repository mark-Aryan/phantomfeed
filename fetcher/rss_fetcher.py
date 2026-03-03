"""
fetcher/rss_fetcher.py
======================
Async multi-feed RSS fetcher.

Supported security RSS feeds (pre-configured):
  - Krebs on Security
  - The Hacker News
  - Bleeping Computer
  - CISA Alerts
  - Threatpost
  - Dark Reading

Additional feeds can be added in config.json under "rss_feeds".
Each feed entry: {"url": "...", "name": "Feed Name"}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

DEFAULT_FEEDS: list[dict[str, str]] = [
    {
        "url":  "https://krebsonsecurity.com/feed/",
        "name": "Krebs on Security",
    },
    {
        "url":  "https://feeds.feedburner.com/TheHackersNews",
        "name": "The Hacker News",
    },
    {
        "url":  "https://www.bleepingcomputer.com/feed/",
        "name": "Bleeping Computer",
    },
    {
        "url":  "https://www.cisa.gov/cybersecurity-advisories/all.xml",
        "name": "CISA",
    },
    {
        "url":  "https://feeds.feedburner.com/securityweek",
        "name": "SecurityWeek",
    },
    {
        "url":  "https://www.darkreading.com/rss.xml",
        "name": "Dark Reading",
    },
]


async def _fetch_one(
    feed: dict[str, str],
    session: aiohttp.ClientSession,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> list[dict[str, Any]]:
    """Fetch and parse a single RSS feed."""
    url = feed["url"]
    name = feed.get("name", url)

    for attempt in range(1, max_retries + 1):
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 429:
                    wait = base_delay * (2 ** attempt)
                    log.warning("RSS rate-limit (%s); waiting %.1fs", name, wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                content = await resp.text()

            import feedparser  # type: ignore
            parsed = feedparser.parse(content)
            entries = []
            for entry in parsed.entries:
                entry["_feed_name"] = name
                entries.append(dict(entry))
            log.info("RSS [%s] fetched %d entries.", name, len(entries))
            return entries

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            wait = base_delay * (2 ** attempt)
            log.warning("RSS [%s] attempt %d failed (%s); retrying in %.1fs",
                        name, attempt, exc, wait)
            await asyncio.sleep(wait)
        except Exception as exc:
            log.error("RSS [%s] unexpected error: %s", name, exc)
            break

    return []


async def fetch(
    feeds: list[dict[str, str]] | None = None,
    *,
    max_retries: int = 3,
    session: aiohttp.ClientSession | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch all RSS feeds concurrently.

    Returns flat list of raw entry dicts (with '_feed_name' injected).
    """
    feeds = feeds or DEFAULT_FEEDS
    own_session = session is None
    if own_session:
        connector = aiohttp.TCPConnector(limit=10)
        session = aiohttp.ClientSession(connector=connector)

    results: list[dict[str, Any]] = []
    try:
        tasks = [_fetch_one(feed, session, max_retries) for feed in feeds]
        batches = await asyncio.gather(*tasks, return_exceptions=True)
        for batch in batches:
            if isinstance(batch, list):
                results.extend(batch)
            else:
                log.error("RSS batch error: %s", batch)
    finally:
        if own_session:
            await session.close()

    log.info("RSS total: %d entries from %d feeds.", len(results), len(feeds))
    return results
