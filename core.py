"""
core.py
=======
Main pipeline orchestrator.

process_item()   – processes one normalised item end-to-end
run_cycle()      – one full fetch-process cycle (all sources)
run_daemon()     – infinite 24×7 loop with configurable intervals
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from fetcher import fetch_newsapi, fetch_nvd, fetch_rss
from generators import generate_caption, generate_image
from pipeline import (
    DedupeDB,
    canonical_id,
    classify,
    normalize,
    safety_check,
    slugify,
)
from pipeline.safety_filter import review_text
from storage import copy_images, item_dir, save_meta, save_post, save_review

log = logging.getLogger(__name__)

# ── Metrics (in-memory counters, exported to status.json each cycle) ──────────
_metrics: dict[str, int] = {
    "fetched": 0,
    "generated": 0,
    "skipped_dupe": 0,
    "skipped_similar": 0,
    "flagged": 0,
    "errors": 0,
}


def _bump(key: str, n: int = 1) -> None:
    _metrics[key] = _metrics.get(key, 0) + n


def get_metrics() -> dict[str, Any]:
    return {**_metrics, "updated_at": datetime.now(timezone.utc).isoformat()}


# ── Single item processor ─────────────────────────────────────────────────────

def process_item(
    item: dict[str, Any],
    db: DedupeDB,
    config: dict[str, Any],
    base_out: str | Path = "out",
) -> str:
    """
    Run one normalised item through the full pipeline.

    Returns: "generated" | "dupe" | "similar" | "flagged" | "error"
    """
    title = item.get("title", "")
    url = item.get("url", "")
    pub = item.get("published_at", "")
    source = item.get("source", "")

    # 1. Canonical ID
    cid = canonical_id(title=title, url=url, published_at=pub, source=source)

    # 2. Dedupe — exact match
    if db.is_processed(cid):
        log.debug("Skipping duplicate: %s", cid)
        _bump("skipped_dupe")
        return "dupe"

    # 3. Fuzzy similarity guard
    sim_threshold = float(config.get("similarity_threshold", 0.92))
    similar_cid = db.find_similar(title, threshold=sim_threshold)
    if similar_cid and similar_cid != cid:
        log.info("Skipping similar item (≥%.2f): '%s'", sim_threshold, title[:60])
        _bump("skipped_similar")
        # Still mark to avoid repeated checks
        db.mark_processed(
            canonical_id=cid, slug=slugify(title),
            category=item.get("category", "news"),
            source=source, url=url, title=title,
            published_at=pub, flagged=False,
        )
        return "similar"

    # 4. Classify
    item["category"] = classify(title, item.get("description", ""))

    # 5. Safety check
    safety = safety_check(item)
    out = item_dir(base_out, item, cid)

    if not safety.is_safe:
        log.warning("Item flagged for manual review: %s", cid)
        review = review_text(item, safety.reasons)
        save_review(out, review)
        save_meta(out, item, cid)
        db.mark_processed(
            canonical_id=cid, slug=slugify(title),
            category=item["category"], source=source,
            url=url, title=title, published_at=pub, flagged=True,
        )
        _bump("flagged")
        return "flagged"

    # 6. Generate caption
    try:
        caption = generate_caption(item, config)
    except Exception as exc:
        log.error("Caption generation failed for %s: %s", cid, exc)
        _bump("errors")
        return "error"

    # 7. Generate image
    try:
        raw_path, final_path = generate_image(item, out, config)
    except Exception as exc:
        log.error("Image generation failed for %s: %s", cid, exc)
        _bump("errors")
        return "error"

    # 8. Save outputs
    save_post(out, caption, item)
    save_meta(out, item, cid)
    copy_images(out, raw_path, final_path)

    # 9. Mark in DB
    db.mark_processed(
        canonical_id=cid, slug=slugify(title),
        category=item["category"], source=source,
        url=url, title=title, published_at=pub, flagged=False,
    )

    log.info("Generated [%s] %s → %s", item["category"], cid, out)
    _bump("generated")
    return "generated"


# ── One full fetch cycle ──────────────────────────────────────────────────────

async def run_cycle(
    config: dict[str, Any],
    db: DedupeDB,
    base_out: str | Path = "out",
) -> dict[str, int]:
    """
    Fetch all enabled sources, normalise, and process each item.

    Returns per-cycle counts dict.
    """
    cycle_counts: dict[str, int] = {
        "fetched": 0, "generated": 0, "dupe": 0,
        "similar": 0, "flagged": 0, "errors": 0,
    }
    raw_items: list[tuple[dict, str]] = []  # (raw_item, fmt)

    async with aiohttp.ClientSession() as session:
        tasks = []

        # NewsAPI
        if config.get("newsapi_key"):
            tasks.append(("newsapi", fetch_newsapi(
                config["newsapi_key"],
                query=config.get("newsapi_query", ""),
                page_size=config.get("newsapi_page_size", 20),
                session=session,
            )))

        # NVD
        if config.get("nvd_enabled", True):
            tasks.append(("nvd", fetch_nvd(
                api_key=config.get("nvd_api_key", ""),
                hours_back=config.get("nvd_hours_back", 24),
                session=session,
            )))

        # RSS
        if config.get("rss_enabled", True):
            from fetcher.rss_fetcher import DEFAULT_FEEDS
            feeds = config.get("rss_feeds") or DEFAULT_FEEDS
            tasks.append(("rss", fetch_rss(feeds=feeds, session=session)))

        results = await asyncio.gather(
            *[t[1] for t in tasks], return_exceptions=True
        )

    for (fmt, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            log.error("Fetch error [%s]: %s", fmt, result)
            continue
        for raw in result:
            raw_items.append((raw, fmt))

    cycle_counts["fetched"] = len(raw_items)
    _bump("fetched", len(raw_items))

    for raw, fmt in raw_items:
        try:
            item = normalize(raw, fmt=fmt)
            status = process_item(item, db, config, base_out)
            cycle_counts[status] = cycle_counts.get(status, 0) + 1
        except Exception as exc:
            log.exception("Unexpected error processing item: %s", exc)
            cycle_counts["errors"] += 1

    # Write status.json
    _write_status(config.get("status_file", "status.json"))
    return cycle_counts


def _write_status(path: str) -> None:
    """Export metrics to a JSON file for health-check / monitoring."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(get_metrics(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── 24×7 daemon loop ──────────────────────────────────────────────────────────

async def run_daemon(
    config: dict[str, Any],
    db: DedupeDB,
    base_out: str | Path = "out",
) -> None:
    """
    Infinite polling loop.  Runs run_cycle() every `poll_interval` seconds.
    Respects a per-source interval: nvd_interval, rss_interval (both default
    to poll_interval).
    """
    poll_interval = float(config.get("poll_interval", 3600))
    log.info("Daemon started. Poll interval: %.0fs", poll_interval)

    while True:
        start = time.monotonic()
        try:
            counts = await run_cycle(config, db, base_out)
            log.info("Cycle complete: %s", counts)
        except Exception as exc:
            log.exception("Cycle error: %s", exc)

        elapsed = time.monotonic() - start
        wait = max(0.0, poll_interval - elapsed)
        log.info("Next cycle in %.0fs.", wait)
        await asyncio.sleep(wait)
