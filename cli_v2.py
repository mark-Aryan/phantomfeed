#!/usr/bin/env python3
"""
cli_v2.py  ★ FINAL FIX ★
==========================
ROOT CAUSE of "unrecognized arguments: --live":

argparse has TWO parsing stages:
  Stage 1: parent parser consumes everything BEFORE the subcommand name
  Stage 2: the chosen subparser consumes everything AFTER the subcommand name

So in:  python cli_v2.py daemon --live
  "daemon" goes to Stage 1 → selects the daemon subparser
  "--live" goes to Stage 2 → daemon subparser tries to handle it
  
BUT --live was only registered on the PARENT parser (Stage 1), not on the
daemon subparser (Stage 2) → "unrecognized arguments: --live"

FIX: Register --live and --depth on EVERY subparser that runs cycles.
Both of these now work:
  python cli_v2.py daemon --live     ← after subcommand  ✅
  python cli_v2.py --live daemon     ← before subcommand ✅ (kept for compat)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import banner as _banner


# ── Logging ───────────────────────────────────────────────────────────────────

def _setup_logging(level: str = "INFO", log_file: str = "logs/app.log") -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            d = {
                "ts":      self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
                "level":   record.levelname,
                "module":  record.module,
                "message": record.getMessage(),
            }
            if record.exc_info:
                d["exc"] = self.formatException(record.exc_info)
            return json.dumps(d)

    fmt      = JsonFormatter()
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5
        ),
    ]
    for h in handlers:
        h.setFormatter(fmt)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=handlers,
    )


# ── Config ────────────────────────────────────────────────────────────────────

def _load_config(path: str = "config.json") -> dict:
    defaults: dict = {
        "poll_interval":          3600,
        "nvd_enabled":            True,
        "nvd_hours_back":         24,
        "rss_enabled":            True,
        "newsapi_page_size":      20,
        "similarity_threshold":   0.92,
        "caption_backend":        "template",
        "caption_depth":          "deep",
        "image_backend":          "placeholder",
        "image_depth":            "deep",
        "image_size":             "linkedin",
        "live_mode":              True,          # DEFAULT: live only
        "live_lookback_minutes":  90,
        "blog_enabled":           True,
        "blog_dir":               "blog",
        "blog_clean_rebuild":     False,
        "autopush_enabled":       False,
        "autopush_mode":          "api",
        "github_token":           "",
        "github_repo":            "",
        "github_branch":          "gh-pages",
        "db_path":                "data/dedupe.db",
        "out_dir":                "out",
        "status_file":            "status.json",
        "log_level":              "INFO",
        "log_file":               "logs/app.log",
        "health_port":            8080,
    }
    cfg_path = Path(path)
    if cfg_path.exists():
        with cfg_path.open() as f:
            defaults.update(json.load(f))

    # Env vars always override config.json
    env_map = {
        "NEWSAPI_KEY":       "newsapi_key",
        "NVD_API_KEY":       "nvd_api_key",
        "HF_API_TOKEN":      "hf_api_token",
        "ANTHROPIC_API_KEY": "claude_api_key",
        "CAPTION_BACKEND":   "caption_backend",
        "IMAGE_BACKEND":     "image_backend",
        "GITHUB_TOKEN":      "github_token",
        "GITHUB_REPO":       "github_repo",
    }
    for env_var, cfg_key in env_map.items():
        val = os.getenv(env_var)
        if val:
            defaults[cfg_key] = val
    return defaults


# ── Health server ─────────────────────────────────────────────────────────────

async def _health_server(port: int, status_file: str) -> None:
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/health", "/", "/status"):
                try:
                    body = Path(status_file).read_bytes()
                    code = 200
                except FileNotFoundError:
                    body = b'{"status":"starting"}'
                    code = 200
            else:
                body, code = b"Not Found", 404
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logging.getLogger(__name__).info("Health-check server on :%d", port)


# ── Seed items ────────────────────────────────────────────────────────────────

SEED_ITEMS = [
    {
        "title": "CVE-2026-1234 — Critical RCE in Apache HTTP Server 2.4",
        "description": (
            "A critical remote code execution vulnerability (CVSS 9.8) "
            "was disclosed in Apache HTTP Server 2.4.x. Unauthenticated "
            "attackers can execute arbitrary code via a malformed HTTP/2 "
            "request header. All 2.4.x versions prior to 2.4.61 affected."
        ),
        "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-1234",
        "published_at": "2026-01-15T12:00:00Z",
        "source": "NVD-Seed",
    },
    {
        "title": "Massive Phishing Campaign Targets Indian Banks (2026)",
        "description": (
            "A large-scale phishing campaign impersonating major Indian banks "
            "detected distributing credential-harvesting pages via WhatsApp and "
            "SMS. Over 50,000 victims reported across 12 states."
        ),
        "url": "https://example.com/phishing-india-2026",
        "published_at": "2026-01-16T08:30:00Z",
        "source": "SecurityWeek-Seed",
    },
    {
        "title": "Ransomware Group Claims Healthcare Provider Breach",
        "description": (
            "The Clop ransomware group claimed responsibility for a breach "
            "affecting a major healthcare provider, exfiltrating 2 TB of "
            "patient records including PII and medical histories."
        ),
        "url": "https://example.com/ransomware-health-2026",
        "published_at": "2026-01-17T10:15:00Z",
        "source": "ThreatPost-Seed",
    },
]


# ── KEY FIX: shared flag helper ───────────────────────────────────────────────

def _add_run_flags(p: argparse.ArgumentParser) -> None:
    """
    Add --live and --depth to a subparser.
    Must be called for EACH subparser that runs fetch/generate cycles.
    This is what fixes "unrecognized arguments: --live".
    """
    p.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Live mode: only fetch articles published since the last run. "
             "If nothing new exists, no posts are created.",
    )
    p.add_argument(
        "--depth",
        choices=["deep", "standard"],
        default=None,
        help="Caption/image depth (default: from config, usually 'deep')",
    )


def _apply_overrides(args: argparse.Namespace, config: dict) -> None:
    """Write CLI flag values into config dict so core_v2 picks them up."""
    if getattr(args, "live", False):
        config["live_mode"] = True
    depth = getattr(args, "depth", None)
    if depth:
        config["caption_depth"] = depth
        config["image_depth"]   = depth


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_start(args: argparse.Namespace, config: dict) -> None:
    _apply_overrides(args, config)
    from core_v2 import run_cycle
    from pipeline.dedupe import DedupeDB

    db     = DedupeDB(config["db_path"])
    counts = asyncio.run(run_cycle(config, db, config["out_dir"]))
    print(f"\n✅ Cycle complete: {json.dumps(counts, indent=2)}")
    db.close()


def cmd_daemon(args: argparse.Namespace, config: dict) -> None:
    _apply_overrides(args, config)
    from core_v2 import run_daemon
    from pipeline.dedupe import DedupeDB

    db   = DedupeDB(config["db_path"])
    loop = asyncio.new_event_loop()
    if config.get("health_port"):
        loop.run_until_complete(
            _health_server(config["health_port"], config["status_file"])
        )
    try:
        loop.run_until_complete(run_daemon(config, db, config["out_dir"]))
    except KeyboardInterrupt:
        print("\nDaemon stopped.")
    finally:
        db.close()
        loop.close()


def cmd_blog(args: argparse.Namespace, config: dict) -> None:
    from publisher.blog_publisher import publish as blog_publish
    clean    = getattr(args, "clean", False) or config.get("blog_clean_rebuild", False)
    blog_dir = config.get("blog_dir", "blog")
    print(f"\n🏗  Building static blog → {blog_dir}/")
    n = blog_publish(out_dir=config["out_dir"], blog_dir=blog_dir, clean=clean)
    print(f"✅ Blog built: {n} posts → {blog_dir}/index.html")


def cmd_status(args: argparse.Namespace, config: dict) -> None:
    from pipeline.dedupe import DedupeDB
    db    = DedupeDB(config["db_path"])
    stats = db.stats()
    db.close()
    print("\n=== PhantomFeed — Status ===")
    for k, v in stats.items():
        print(f"  {k:20s}: {v}")
    sf = Path(config["status_file"])
    if sf.exists():
        print("\nLatest metrics:")
        print(sf.read_text())
    blog_dir = Path(config.get("blog_dir", "blog"))
    if blog_dir.exists():
        posts_dir = blog_dir / "posts"
        count = len(list(posts_dir.glob("*/index.html"))) if posts_dir.exists() else 0
        print(f"\nBlog: {blog_dir}/index.html  ({count} posts)")


def cmd_reprocess(args: argparse.Namespace, config: dict) -> None:
    from pipeline.dedupe import DedupeDB
    db = DedupeDB(config["db_path"])
    ok = db.delete(args.id)
    db.close()
    if ok:
        print(f"✅ Deleted {args.id!r} — run 'start' to reprocess.")
    else:
        print(f"⚠️  ID {args.id!r} not found.")


def cmd_purge(args: argparse.Namespace, config: dict) -> None:
    confirm = input("⚠️  Delete ALL records? Type YES to confirm: ")
    if confirm.strip() != "YES":
        print("Aborted.")
        return
    from pipeline.dedupe import DedupeDB
    db = DedupeDB(config["db_path"])
    n  = db.purge()
    db.close()
    print(f"✅ Purged {n} records.")


def cmd_seed(args: argparse.Namespace, config: dict) -> None:
    _apply_overrides(args, config)
    # Force live_mode OFF for seed — seed uses fixed items, not live feeds
    config["live_mode"] = False
    from core_v2 import process_item
    from pipeline import normalize
    from pipeline.dedupe import DedupeDB

    db = DedupeDB(config["db_path"])
    print(f"\nSeeding {len(SEED_ITEMS)} test items...")
    for raw in SEED_ITEMS:
        item   = normalize(raw, fmt="rss")
        result = process_item(item, db, config, config["out_dir"])
        print(f"  [{result:10s}] {raw['title'][:70]}")
    db.close()
    print(f"\n✅ Seed complete → {config['out_dir']}/")

    # Build blog after seeding
    if config.get("blog_enabled", True):
        cmd_blog(args, config)

    # Push to GitHub after seeding if autopush enabled
    if config.get("autopush_enabled", False):
        from publisher.git_autopush import autopush
        pushed = autopush(
            config=config,
            blog_dir=config.get("blog_dir", "blog"),
            out_dir=config["out_dir"],
            post_count=len(SEED_ITEMS),
        )
        if pushed:
            print(f"✅ Pushed seed posts to GitHub → {config.get('github_branch','gh-pages')}")
        else:
            print("⚠️  Auto-push failed — check GITHUB_TOKEN in your .env file")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    # ── Root parser ──────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        prog="phantomfeed-v2",
        description="PhantomFeed v2 — Cybersecurity news automation",
    )
    parser.add_argument("--config",   default="config.json")
    parser.add_argument("--loglevel", default=None,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    sub = parser.add_subparsers(dest="command", required=True)

    # ── start ─────────────────────────────────────────────────────────────────
    p_start = sub.add_parser("start", help="Run one fetch+generate cycle")
    _add_run_flags(p_start)   # <-- KEY FIX: --live registered on subparser

    # ── daemon ────────────────────────────────────────────────────────────────
    p_daemon = sub.add_parser("daemon", help="Run 24×7 continuous daemon")
    _add_run_flags(p_daemon)  # <-- KEY FIX: --live registered on subparser

    # ── blog ──────────────────────────────────────────────────────────────────
    p_blog = sub.add_parser("blog", help="Build/rebuild static blog from out/")
    p_blog.add_argument("--clean", action="store_true",
                        help="Full rebuild — delete blog/ before regenerating")

    # ── status ────────────────────────────────────────────────────────────────
    sub.add_parser("status", help="Show DB stats and last-run metrics")

    # ── purge ─────────────────────────────────────────────────────────────────
    sub.add_parser("purge", help="Purge all DB records (destructive)")

    # ── seed ──────────────────────────────────────────────────────────────────
    p_seed = sub.add_parser("seed", help="Generate test posts without API keys")
    _add_run_flags(p_seed)

    # ── healthcheck ───────────────────────────────────────────────────────────
    sub.add_parser("healthcheck", help="Start health-check HTTP server")

    # ── reprocess ─────────────────────────────────────────────────────────────
    p_rp = sub.add_parser("reprocess", help="Force-reprocess a canonical ID")
    p_rp.add_argument("id")

    # ── Parse + dispatch ──────────────────────────────────────────────────────
    args   = parser.parse_args()
    config = _load_config(args.config)

    if args.loglevel:
        config["log_level"] = args.loglevel

    _setup_logging(config.get("log_level", "INFO"), config.get("log_file", "logs/app.log"))

    _banner.show(
        command=args.command,
        db_path=config.get("db_path", "data/dedupe.db"),
        status_file=config.get("status_file", "status.json"),
    )

    dispatch = {
        "start":       cmd_start,
        "daemon":      cmd_daemon,
        "blog":        cmd_blog,
        "status":      cmd_status,
        "reprocess":   cmd_reprocess,
        "purge":       cmd_purge,
        "seed":        cmd_seed,
        "healthcheck": lambda a, c: asyncio.run(
            _health_server(c.get("health_port", 8080), c.get("status_file", "status.json"))
        ),
    }
    dispatch[args.command](args, config)


if __name__ == "__main__":
    main()
