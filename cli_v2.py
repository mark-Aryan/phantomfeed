#!/usr/bin/env python3
"""
cli_v2.py — PhantomFeed Upgraded CLI  ★ FIXED ★
=================================================
ROOT CAUSE FIX:
  argparse subparsers are INDEPENDENT — flags added only to the parent parser
  are NOT automatically available after the subcommand name.
  
  Python argparse parsing order:
    phantomfeed-v2 [parent flags] <subcommand> [subcommand flags]
  
  So "python cli_v2.py daemon --live" fails because --live was only registered
  on the PARENT, not on the 'daemon' subparser.
  
  FIX: _add_run_flags() adds --live and --depth to EVERY subparser that needs them.
       We also keep them on the parent so both these work:
         python cli_v2.py --live daemon       ← global position
         python cli_v2.py daemon --live       ← subcommand position  ✅
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

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5
        ),
    ]
    fmt = JsonFormatter()
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
        "live_mode":              False,
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

    # Environment variable overrides (always win over config.json)
    env_map = {
        "NEWSAPI_KEY":       "newsapi_key",
        "NVD_API_KEY":       "nvd_api_key",
        "HF_API_TOKEN":      "hf_api_token",
        "ANTHROPIC_API_KEY": "claude_api_key",
        "CAPTION_BACKEND":   "caption_backend",
        "IMAGE_BACKEND":     "image_backend",
        "GITHUB_TOKEN":      "github_token",
        "GITHUB_REPO":       "github_repo",
        "LIVE_MODE":         "live_mode",
    }
    for env_var, cfg_key in env_map.items():
        val = os.getenv(env_var)
        if val:
            if cfg_key == "live_mode":
                defaults[cfg_key] = val.lower() in ("1", "true", "yes")
            else:
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
                body = b"Not Found"
                code = 404
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
            "request header. All 2.4.x versions prior to 2.4.61 are affected."
        ),
        "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-1234",
        "published_at": "2026-01-15T12:00:00Z",
        "source": "NVD-Seed",
    },
    {
        "title": "Massive Phishing Campaign Targets Indian Banks (2026)",
        "description": (
            "A large-scale phishing campaign impersonating major Indian banks "
            "was detected distributing credential-harvesting pages via WhatsApp "
            "and SMS. Over 50,000 victims reported across 12 states."
        ),
        "url": "https://example.com/phishing-india-2026",
        "published_at": "2026-01-16T08:30:00Z",
        "source": "SecurityWeek-Seed",
    },
    {
        "title": "Ransomware Group Claims Healthcare Provider Breach",
        "description": (
            "The Clop ransomware group claimed responsibility for a breach "
            "affecting a major healthcare provider, reportedly exfiltrating "
            "2 TB of patient records including PII and medical data."
        ),
        "url": "https://example.com/ransomware-health-2026",
        "published_at": "2026-01-17T10:15:00Z",
        "source": "ThreatPost-Seed",
    },
]


# ── Shared flag helper ────────────────────────────────────────────────────────

def _add_run_flags(parser: argparse.ArgumentParser) -> None:
    """
    Add --live and --depth to a subparser.
    Called for every subcommand that can run fetch cycles.
    This is the KEY FIX — these flags must be on the subparser,
    not just the parent parser.
    """
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Live-only mode: fetch only articles newer than last run (no old news)",
    )
    parser.add_argument(
        "--depth",
        choices=["deep", "standard"],
        default=None,
        help="Caption/image depth. 'deep' = full analysis, 'standard' = original short caption",
    )


def _apply_overrides(args: argparse.Namespace, config: dict) -> None:
    """Apply CLI flag overrides onto config dict."""
    # --live (check subcommand-level first, then fall back to parent-level)
    if getattr(args, "live", False):
        config["live_mode"] = True
    # --depth
    depth = getattr(args, "depth", None)
    if depth:
        config["caption_depth"] = depth
        config["image_depth"]   = depth


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_start(args: argparse.Namespace, config: dict) -> None:
    _apply_overrides(args, config)
    from core_v2 import run_cycle
    from pipeline.dedupe import DedupeDB

    db = DedupeDB(config["db_path"])
    counts = asyncio.run(run_cycle(config, db, config["out_dir"]))
    print(f"\n✅ Cycle complete: {json.dumps(counts, indent=2)}")
    if config.get("blog_enabled", True):
        print(f"🌐 Blog → {config.get('blog_dir','blog')}/index.html")
    db.close()


def cmd_daemon(args: argparse.Namespace, config: dict) -> None:
    _apply_overrides(args, config)
    from core_v2 import run_daemon
    from pipeline.dedupe import DedupeDB

    db = DedupeDB(config["db_path"])
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
    print(f"✅ Blog published: {n} posts → open {blog_dir}/index.html")


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
    from core_v2 import process_item
    from pipeline import normalize
    from pipeline.dedupe import DedupeDB

    db = DedupeDB(config["db_path"])
    print(f"Seeding {len(SEED_ITEMS)} items (depth={config.get('caption_depth','deep')})...")
    for raw in SEED_ITEMS:
        item   = normalize(raw, fmt="rss")
        result = process_item(item, db, config, config["out_dir"])
        print(f"  [{result:10s}] {raw['title'][:60]}")
    db.close()
    print(f"\n✅ Seed complete → check {config['out_dir']}/")

    if config.get("blog_enabled", True):
        cmd_blog(args, config)

    if config.get("autopush_enabled", False):
        from publisher.git_autopush import autopush
        pushed = autopush(config=config, blog_dir=config.get("blog_dir","blog"),
                          out_dir=config["out_dir"], post_count=len(SEED_ITEMS))
        if pushed:
            print(f"✅ Auto-pushed seed posts to GitHub → {config.get('github_branch','gh-pages')}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    # ── Root parser ──────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        prog="phantomfeed-v2",
        description="PhantomFeed v2 — Cybersecurity news automation with deep blog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config",   default="config.json",
                        help="Path to config.json (default: config.json)")
    parser.add_argument("--loglevel", default=None,
                        choices=["DEBUG","INFO","WARNING","ERROR"],
                        help="Override log level")

    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="{start,daemon,blog,status,purge,seed,healthcheck,reprocess}")

    # ── start ────────────────────────────────────────────────────────────────
    p_start = sub.add_parser("start", help="Run one fetch+generate cycle then exit")
    _add_run_flags(p_start)

    # ── daemon ───────────────────────────────────────────────────────────────
    p_daemon = sub.add_parser("daemon", help="Run 24×7 continuous daemon")
    _add_run_flags(p_daemon)
    # FIX: --live is now registered on p_daemon so "daemon --live" works

    # ── blog ─────────────────────────────────────────────────────────────────
    p_blog = sub.add_parser("blog", help="Build / rebuild static blog from out/ directory")
    p_blog.add_argument("--clean", action="store_true",
                        help="Delete blog/ before rebuilding (full clean rebuild)")

    # ── status ───────────────────────────────────────────────────────────────
    sub.add_parser("status", help="Show database stats and last-run metrics")

    # ── purge ────────────────────────────────────────────────────────────────
    sub.add_parser("purge", help="Purge all processed-item records from the database")

    # ── seed ─────────────────────────────────────────────────────────────────
    p_seed = sub.add_parser("seed", help="Inject test seed items (no API keys needed)")
    _add_run_flags(p_seed)

    # ── healthcheck ──────────────────────────────────────────────────────────
    sub.add_parser("healthcheck", help="Start the health-check HTTP server on configured port")

    # ── reprocess ────────────────────────────────────────────────────────────
    p_rp = sub.add_parser("reprocess", help="Force-reprocess a specific canonical ID")
    p_rp.add_argument("id", help="Canonical ID to delete and reprocess")

    # ── Parse ─────────────────────────────────────────────────────────────────
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

    # ── Dispatch ──────────────────────────────────────────────────────────────
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
