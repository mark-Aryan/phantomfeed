"""
core_v2.py
===========
UPGRADED orchestrator — drop-in replacement for core.py.

Adds:
  1. Deep captions (generators/deep_caption.py)
  2. Deep two-panel images (generators/deep_image.py)
  3. Live-only news pulling (fetcher/live_puller.py)
  4. Blog publishing after each cycle (publisher/blog_publisher.py)

BACKWARD COMPATIBLE:
  • All original imports still work
  • Old config.json values still respected
  • New config keys are additive (all optional, safe defaults)

New config keys:
  caption_depth:         "deep"     | "standard"   (default: "deep")
  image_depth:           "deep"     | "standard"   (default: "deep")
  live_mode:             true       | false         (default: false  — uses original fetchers)
  live_lookback_minutes: 90                         (minutes back on first run)
  blog_enabled:          true       | false         (default: true)
  blog_dir:              "blog"                     (output folder for static site)
  blog_clean_rebuild:    false                      (wipe blog/ before rebuild)
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

log = logging.getLogger(__name__)

# ── Keep original metrics dict ────────────────────────────────────────────────
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


# ── Item processor (upgraded) ──────────────────────────────────────────────────

def process_item(
    item: dict[str, Any],
    db,
    config: dict[str, Any],
    base_out: str | Path = "out",
) -> str:
    """
    Full pipeline for one normalised item.
    Uses deep caption + deep image if configured (default).
    """
    from pipeline import (
        canonical_id, classify, safety_check, slugify,
    )
    from pipeline.safety_filter import review_text
    from storage import copy_images, item_dir, save_meta, save_post, save_review

    title       = item.get("title", "")
    url         = item.get("url", "")
    pub         = item.get("published_at", "")
    source      = item.get("source", "")
    caption_depth = config.get("caption_depth", "deep")
    image_depth   = config.get("image_depth", "deep")

    cid = canonical_id(title=title, url=url, published_at=pub, source=source)

    if db.is_processed(cid):
        log.debug("Skipping duplicate: %s", cid)
        _bump("skipped_dupe")
        return "dupe"

    sim_threshold = float(config.get("similarity_threshold", 0.92))
    similar_cid = db.find_similar(title, threshold=sim_threshold)
    if similar_cid and similar_cid != cid:
        log.info("Skipping similar item (≥%.2f): '%s'", sim_threshold, title[:60])
        _bump("skipped_similar")
        db.mark_processed(
            canonical_id=cid, slug=slugify(title),
            category=item.get("category", "news"),
            source=source, url=url, title=title,
            published_at=pub, flagged=False,
        )
        return "similar"

    item["category"] = classify(title, item.get("description", ""))
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

    # ── Caption (deep or standard) ────────────────────────────────────────
    try:
        if caption_depth == "deep":
            from generators.deep_caption import generate as generate_caption
        else:
            from generators.text_generator import generate as generate_caption
        caption = generate_caption(item, config)
    except Exception as exc:
        log.error("Caption generation failed for %s: %s", cid, exc)
        _bump("errors")
        return "error"

    # ── Image (deep or standard) ──────────────────────────────────────────
    try:
        if image_depth == "deep":
            from generators.deep_image import generate as generate_image
        else:
            from generators.image_generator import generate as generate_image
        raw_path, final_path = generate_image(item, out, config)
    except Exception as exc:
        log.error("Image generation failed for %s: %s", cid, exc)
        _bump("errors")
        return "error"

    save_post(out, caption, item)
    save_meta(out, item, cid)
    copy_images(out, raw_path, final_path)

    db.mark_processed(
        canonical_id=cid, slug=slugify(title),
        category=item["category"], source=source,
        url=url, title=title, published_at=pub, flagged=False,
    )

    log.info("Generated [%s] %s → %s", item["category"], cid, out)
    _bump("generated")
    return "generated"


# ── Cycle ─────────────────────────────────────────────────────────────────────

async def run_cycle(
    config: dict[str, Any],
    db,
    base_out: str | Path = "out",
) -> dict[str, int]:
    """
    One full fetch-process cycle.
    Respects config['live_mode']:
      - True  → live_puller (cursor-based, only new items)
      - False → original fetchers (original behaviour preserved)
    """
    from pipeline import normalize

    cycle_counts: dict[str, int] = {
        "fetched": 0, "generated": 0, "dupe": 0,
        "similar": 0, "flagged": 0, "errors": 0,
    }
    raw_items: list[tuple[dict, str]] = []

    live_mode = config.get("live_mode", False)

    if live_mode:
        # ── LIVE mode (Upgrade #2) ──────────────────────────────────────
        from fetcher.live_puller import CursorStore, pull_live
        cursor = CursorStore(config.get("db_path", "data/dedupe.db"))
        try:
            live_results = await pull_live(config, cursor)
            for newsapi_item in live_results.get("newsapi", []):
                raw_items.append((newsapi_item, "newsapi"))
            for nvd_item in live_results.get("nvd", []):
                raw_items.append((nvd_item, "nvd"))
            for rss_item in live_results.get("rss", []):
                raw_items.append((rss_item, "rss"))
        finally:
            cursor.close()
    else:
        # ── ORIGINAL mode — unchanged ───────────────────────────────────
        from fetcher import fetch_newsapi, fetch_nvd, fetch_rss

        async with aiohttp.ClientSession() as session:
            tasks = []
            if config.get("newsapi_key"):
                tasks.append(("newsapi", fetch_newsapi(
                    config["newsapi_key"],
                    query=config.get("newsapi_query", ""),
                    page_size=config.get("newsapi_page_size", 20),
                    session=session,
                )))
            if config.get("nvd_enabled", True):
                tasks.append(("nvd", fetch_nvd(
                    api_key=config.get("nvd_api_key", ""),
                    hours_back=config.get("nvd_hours_back", 24),
                    session=session,
                )))
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

    _write_status(config.get("status_file", "status.json"))

    # ── Blog publish (Upgrade #3) ─────────────────────────────────────────
    blog_dir  = config.get("blog_dir", "blog")
    new_posts = cycle_counts.get("generated", 0)

    if config.get("blog_enabled", True):
        try:
            from publisher.blog_publisher import publish as blog_publish
            n = blog_publish(
                out_dir=base_out,
                blog_dir=blog_dir,
                clean=config.get("blog_clean_rebuild", False),
            )
            log.info("Blog updated: %d posts published to %s", n, blog_dir)
        except Exception as exc:
            log.warning("Blog publish failed (non-fatal): %s", exc)

    # ── Auto-push to GitHub (Upgrade #4) ──────────────────────────────────
    if config.get("autopush_enabled", False) and new_posts > 0:
        try:
            from publisher.git_autopush import autopush
            pushed = autopush(
                config=config,
                blog_dir=blog_dir,
                out_dir=base_out,
                post_count=new_posts,
            )
            if pushed:
                log.info("✅ Auto-pushed %d new posts to GitHub", new_posts)
            else:
                log.warning("⚠️  Auto-push failed — check GITHUB_TOKEN and GITHUB_REPO")
        except Exception as exc:
            log.warning("Auto-push error (non-fatal): %s", exc)
    elif config.get("autopush_enabled", False) and new_posts == 0:
        log.info("[AutoPush] No new posts this cycle — skipping push")

    return cycle_counts


def _write_status(path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(get_metrics(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


async def run_daemon(
    config: dict[str, Any],
    db,
    base_out: str | Path = "out",
) -> None:
    poll_interval = float(config.get("poll_interval", 3600))
    log.info(
        "Daemon started (live_mode=%s). Poll interval: %.0fs",
        config.get("live_mode", False), poll_interval,
    )
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
