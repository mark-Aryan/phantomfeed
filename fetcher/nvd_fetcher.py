"""
fetcher/nvd_fetcher.py
======================
Async fetcher for NIST NVD CVE feed (free, no API key required for basic use).
Endpoint: https://services.nvd.nist.gov/rest/json/cves/2.0

NVD rate limits:
  - Without API key: 5 requests per 30s rolling window
  - With API key   : 50 requests per 30s
  Register at: https://nvd.nist.gov/developers/request-an-api-key

Fetches CVEs published/modified in the last `hours_back` hours.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


async def fetch(
    *,
    api_key: str = "",
    hours_back: int = 24,
    results_per_page: int = 50,
    min_cvss: float = 0.0,
    max_retries: int = 4,
    base_delay: float = 6.0,
    session: aiohttp.ClientSession | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch recently published/modified CVEs from NVD.

    Returns list of raw CVE dicts (normalizer converts these).
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)
    pub_start = start.strftime("%Y-%m-%dT%H:%M:%S.000")
    pub_end   = now.strftime("%Y-%m-%dT%H:%M:%S.000")

    params: dict[str, Any] = {
        "pubStartDate": pub_start,
        "pubEndDate":   pub_end,
        "resultsPerPage": results_per_page,
    }
    if min_cvss > 0:
        params["cvssV3Severity"] = _cvss_label(min_cvss)

    headers = {}
    if api_key:
        headers["apiKey"] = api_key

    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession(headers=headers)

    cves: list[dict[str, Any]] = []
    try:
        for attempt in range(1, max_retries + 1):
            try:
                async with session.get(
                    NVD_URL, params=params,
                    timeout=aiohttp.ClientTimeout(total=45),
                ) as resp:
                    if resp.status == 429:
                        wait = base_delay * (2 ** attempt)
                        log.warning("NVD rate-limit; waiting %.1fs", wait)
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
                    raw_cves = data.get("vulnerabilities", [])
                    for v in raw_cves:
                        cve = v.get("cve", {})
                        cve["_fetcher"] = "nvd"
                        cves.append(cve)
                    log.info("NVD fetched %d CVEs (hours_back=%d).", len(cves), hours_back)
                    break
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                wait = base_delay * (2 ** attempt)
                log.warning("NVD attempt %d failed (%s); retrying in %.1fs", attempt, exc, wait)
                await asyncio.sleep(wait)
    finally:
        if own_session:
            await session.close()

    return cves


def _cvss_label(score: float) -> str:
    if score >= 9.0:
        return "CRITICAL"
    elif score >= 7.0:
        return "HIGH"
    elif score >= 4.0:
        return "MEDIUM"
    return "LOW"
