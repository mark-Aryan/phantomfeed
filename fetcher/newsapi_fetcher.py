"""
fetcher/newsapi_fetcher.py
==========================
Async fetcher for NewsAPI.org (free tier: 100 req/day).
Endpoint: /v2/everything with cybersecurity keywords.

Free-tier notes:
  - Max 100 requests/day; use a long poll_interval (e.g., 3600s)
  - Results limited to past 30 days
  - Register at https://newsapi.org/register for a free API key
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

BASE_URL = "https://newsapi.org/v2/everything"
DEFAULT_QUERY = (
    "cybersecurity OR CVE OR vulnerability OR \"data breach\" "
    "OR \"ransomware\" OR \"ethical hacking\" OR \"penetration testing\""
)


async def fetch(
    api_key: str,
    *,
    query: str = DEFAULT_QUERY,
    language: str = "en",
    page_size: int = 20,
    max_retries: int = 3,
    base_delay: float = 2.0,
    session: aiohttp.ClientSession | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch latest cybersecurity news from NewsAPI.

    Returns list of raw article dicts (normalizer converts these).
    """
    params = {
        "q": query,
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": api_key,
    }

    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()

    articles: list[dict[str, Any]] = []
    try:
        for attempt in range(1, max_retries + 1):
            try:
                async with session.get(
                    BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 429:
                        wait = base_delay * (2 ** attempt)
                        log.warning("NewsAPI rate-limit hit; waiting %.1fs", wait)
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    articles = data.get("articles", [])
                    for a in articles:
                        a["_fetcher"] = "newsapi"
                    log.info("NewsAPI fetched %d articles.", len(articles))
                    break
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                wait = base_delay * (2 ** attempt)
                log.warning("NewsAPI attempt %d failed (%s); retrying in %.1fs", attempt, exc, wait)
                await asyncio.sleep(wait)
    finally:
        if own_session:
            await session.close()

    return articles
