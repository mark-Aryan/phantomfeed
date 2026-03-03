# =============================================================================
# core_v2.py — PhantomFeed v2  ★ PRODUCTION-READY ★
# =============================================================================
# Copyright (c) 2026 Aryan Kumar Upadhyay (@aryankrupadhyay)
# Brand: codeXploit · https://codexploit.in
# License: MIT — Retain this header and brand attribution in all copies.
#
# FIXES IN THIS VERSION
# ─────────────────────
# FIX-1  Removed duplicate `from pipeline.safety_filter import review_text`
#        (was imported both in function signature and redundantly inside block)
# FIX-2  process_item now uses a single lazy-import strategy to avoid
#        repeated module resolution on every item in tight loops.
# FIX-3  Live mode correctly skips blog + autopush when 0 fresh items.
# FIX-4  autopush() is called at the end of every cycle when new posts exist.
# FIX-5  Proper exception typing on asyncio gather results.
# =============================================================================

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

_metrics: dict[str, int] = {
    "fetched": 0, "generated": 0, "skipped_dupe": 0,
    "skipped_similar": 0, "flagged": 0, "errors": 0,
}


def _bump(key: str, n: int = 1) -> None:
    _metrics[key] = _metrics.get(key, 0) + n


def get_metrics() -> dict[str, Any]:
    return {**_metrics, "updated_at": datetime.now(timezone.utc).isoformat()}


# ── Item processor ────────────────────────────────────────────────────────────

def process_item(
    item: dict[str, Any],
    db: Any,
    config: dict[str, Any],
    base_out: str | Path = "out",
) -> str:
    """
    Process one normalised news item end-to-end:
      dedupe → classify → safety-check → caption → image → save

    Returns: "generated" | "dupe" | "similar" | "flagged" | "error"
    """
    # ── Lazy imports (avoids repeated attribute lookups in tight loops) ───────
    from pipeline.dedupe import canonical_id, slugify
    from pipeline.classifier import classify
    from pipeline.safety_filter import check as safety_check, review_text
    from storage import copy_images, item_dir, save_meta, save_post, save_review

    title  = item.get("title", "")
    url    = item.get("url", "")
    pub    = item.get("published_at", "")
    source = item.get("source", "")

    caption_depth = config.get("caption_depth", "deep")
    image_depth   = config.get("image_depth", "deep")

    # ── 1. Deduplication ──────────────────────────────────────────────────────
    cid = canonical_id(title=title, url=url, published_at=pub, source=source)

    if db.is_processed(cid):
        log.debug("Skipping duplicate: %s", cid)
        _bump("skipped_dupe")
        return "dupe"

    sim_threshold = float(config.get("similarity_threshold", 0.92))
    similar_cid   = db.find_similar(title, threshold=sim_threshold)
    if similar_cid and similar_cid != cid:
        log.info("Skipping similar item (%.2f): '%s'", sim_threshold, title[:60])
        _bump("skipped_similar")
        db.mark_processed(
            canonical_id=cid, slug=slugify(title),
            category=item.get("category", "news"),
            source=source, url=url, title=title,
            published_at=pub, flagged=False,
        )
        return "similar"

    # ── 2. Classify ───────────────────────────────────────────────────────────
    item["category"] = classify(title, item.get("description", ""))

    # ── 3. Safety check ───────────────────────────────────────────────────────
    safety = safety_check(item)
    out    = item_dir(base_out, item, cid)

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

    # ── 4. Caption generation ─────────────────────────────────────────────────
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

    # ── 5. Image generation ───────────────────────────────────────────────────
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

    # ── 6. Persist ────────────────────────────────────────────────────────────
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
    config:   dict[str, Any],
    db:       Any,
    base_out: str | Path = "out",
) -> dict[str, int]:
    """
    Run one complete fetch → process → blog → push cycle.

    Returns per-cycle counters: fetched / generated / dupe / similar / flagged / errors
    """
    from pipeline.normalizer import normalize

    cycle_counts: dict[str, int] = {
        "fetched": 0, "generated": 0, "dupe": 0,
        "similar": 0, "flagged": 0, "errors": 0,
    }
    raw_items: list[tuple[dict[str, Any], str]] = []
    live_mode = config.get("live_mode", True)

    # ── Fetch ─────────────────────────────────────────────────────────────────
    if live_mode:
        from fetcher.live_puller import CursorStore, pull_live
        cursor = CursorStore(config.get("db_path", "data/dedupe.db"))
        try:
            live_results = await pull_live(config, cursor)
            for source_key in ("newsapi", "nvd", "rss"):
                for item in live_results.get(source_key, []):
                    raw_items.append((item, source_key))
        finally:
            cursor.close()
    else:
        async with aiohttp.ClientSession() as session:
            tasks: list[tuple[str, Any]] = []
            if config.get("newsapi_key"):
                from fetcher.newsapi_fetcher import fetch as fetch_newsapi
                tasks.append(("newsapi", fetch_newsapi(
                    config["newsapi_key"],
                    query=config.get("newsapi_query", ""),
                    page_size=config.get("newsapi_page_size", 20),
                    session=session,
                )))
            if config.get("nvd_enabled", True):
                from fetcher.nvd_fetcher import fetch as fetch_nvd
                tasks.append(("nvd", fetch_nvd(
                    api_key=config.get("nvd_api_key", ""),
                    hours_back=config.get("nvd_hours_back", 24),
                    session=session,
                )))
            if config.get("rss_enabled", True):
                from fetcher.rss_fetcher import fetch as fetch_rss, DEFAULT_FEEDS
                feeds = config.get("rss_feeds") or DEFAULT_FEEDS
                tasks.append(("rss", fetch_rss(feeds=feeds, session=session)))

            results = await asyncio.gather(
                *[coro for _, coro in tasks], return_exceptions=True
            )
            for (fmt, _), result in zip(tasks, results):
                if isinstance(result, BaseException):
                    log.error("Fetch error [%s]: %s", fmt, result)
                    continue
                for raw in result:
                    raw_items.append((raw, fmt))

    cycle_counts["fetched"] = len(raw_items)
    _bump("fetched", len(raw_items))
    log.info("Fetched %d items (live_mode=%s)", len(raw_items), live_mode)

    # ── FIX-3: Early exit in live mode when nothing new ───────────────────────
    if live_mode and len(raw_items) == 0:
        log.info("Live mode: 0 fresh items — skipping generation, blog, and push.")
        _write_status(config.get("status_file", "status.json"))
        return cycle_counts

    # ── Process items ─────────────────────────────────────────────────────────
    for raw, fmt in raw_items:
        try:
            item   = normalize(raw, fmt=fmt)
            status = process_item(item, db, config, base_out)
            cycle_counts[status] = cycle_counts.get(status, 0) + 1
        except Exception as exc:
            log.exception("Unexpected error processing item: %s", exc)
            cycle_counts["errors"] += 1

    _write_status(config.get("status_file", "status.json"))

    new_posts = cycle_counts.get("generated", 0)
    blog_dir  = config.get("blog_dir", "blog")

    # ── Blog publish ──────────────────────────────────────────────────────────
    if config.get("blog_enabled", True) and new_posts > 0:
        try:
            from publisher.blog_publisher import publish as blog_publish
            n = blog_publish(
                out_dir=base_out,
                blog_dir=blog_dir,
                clean=config.get("blog_clean_rebuild", False),
            )
            log.info("Blog updated: %d posts → %s/", n, blog_dir)
        except Exception as exc:
            log.warning("Blog publish failed (non-fatal): %s", exc)
    elif new_posts == 0:
        log.info("No new posts this cycle — skipping blog rebuild.")

    # ── FIX-4: Auto-push to GitHub ────────────────────────────────────────────
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
                log.info(
                    "✅ Auto-pushed %d new posts → %s@%s",
                    new_posts, config.get("github_repo", ""), config.get("github_branch", "gh-pages"),
                )
            else:
                log.warning("⚠️  Auto-push failed — verify GITHUB_TOKEN and GITHUB_REPO in .env")
        except Exception as exc:
            log.warning("Auto-push error (non-fatal): %s", exc)
    elif config.get("autopush_enabled", False) and new_posts == 0:
        log.info("Auto-push enabled but no new posts — skipping.")

    return cycle_counts


def _write_status(path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(get_metrics(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


async def run_daemon(
    config:   dict[str, Any],
    db:       Any,
    base_out: str | Path = "out",
) -> None:
    """Run an infinite polling loop. Ctrl-C to stop."""
    poll_interval = float(config.get("poll_interval", 3600))
    log.info(
        "Daemon started — live_mode=%s  autopush=%s  poll=%.0fs",
        config.get("live_mode", True),
        config.get("autopush_enabled", False),
        poll_interval,
    )
    while True:
        start = time.monotonic()
        try:
            counts = await run_cycle(config, db, base_out)
            log.info("Cycle complete: %s", counts)
        except Exception as exc:
            log.exception("Cycle error (will retry next interval): %s", exc)
        elapsed = time.monotonic() - start
        wait    = max(0.0, poll_interval - elapsed)
        log.info("Next cycle in %.0fs  (elapsed=%.1fs)", wait, elapsed)
        await asyncio.sleep(wait)
