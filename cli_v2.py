#!/usr/bin/env python3
"""
cli_v2.py — PhantomFeed Upgraded CLI
======================================
Drop-in replacement for cli.py with 3 new capabilities:

  1. Deep captions & images (--depth deep|standard)
  2. Live-only news pulling  (--live flag or live_mode in config)
  3. Blog publishing         (python cli_v2.py blog)

All original commands still work unchanged.

Usage:
  python cli_v2.py start              # run one cycle (original)
  python cli_v2.py start --live       # live-only cycle (no old news)
  python cli_v2.py start --depth deep # deep caption+image (default)
  python cli_v2.py daemon             # 24×7 daemon
  python cli_v2.py daemon --live      # 24×7 live-only daemon
  python cli_v2.py blog               # build/rebuild static blog site
  python cli_v2.py blog --clean       # clean-rebuild blog
  python cli_v2.py status             # show metrics / DB stats
  python cli_v2.py seed               # inject sample items
  python cli_v2.py reprocess <id>     # delete ID and reprocess
  python cli_v2.py purge              # delete all DB records
  python cli_v2.py healthcheck        # start HTTP health-check server
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


# ── Logging setup (identical to cli.py) ──────────────────────────────────────

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
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), handlers=handlers)


# ── Config loader (extends cli.py loader) ─────────────────────────────────────

def _load_config(path: str = "config.json") -> dict:
    defaults: dict = {
        "poll_interval":          3600,
        "nvd_enabled":            True,
        "nvd_hours_back":         24,
        "rss_enabled":            True,
        "newsapi_page_size":      20,
        "similarity_threshold":   0.92,
        "caption_backend":        "template",
        "caption_depth":          "deep",       # NEW
        "image_backend":          "placeholder",
        "image_depth":            "deep",        # NEW
        "image_size":             "linkedin",
        "live_mode":              False,         # NEW
        "live_lookback_minutes":  90,            # NEW
        "blog_enabled":           True,          # NEW
        "blog_dir":               "blog",        # NEW
        "blog_clean_rebuild":     False,         # NEW
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

    env_map = {
        "NEWSAPI_KEY":       "newsapi_key",
        "NVD_API_KEY":       "nvd_api_key",
        "HF_API_TOKEN":      "hf_api_token",
        "ANTHROPIC_API_KEY": "claude_api_key",
        "CAPTION_BACKEND":   "caption_backend",
        "IMAGE_BACKEND":     "image_backend",
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


# ── Health-check (identical to cli.py) ────────────────────────────────────────

async def _health_server(port: int, status_file: str) -> None:
    import http.server, threading

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

        def log_message(self, *_): pass

    server = http.server.HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logging.getLogger(__name__).info("Health-check server on :%d", port)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_start(args, config: dict) -> None:
    """Run one fetch cycle and exit."""
    # Apply CLI overrides
    if getattr(args, "live", False):
        config["live_mode"] = True
    if getattr(args, "depth", None):
        config["caption_depth"] = args.depth
        config["image_depth"]   = args.depth

    from core_v2 import run_cycle
    from pipeline.dedupe import DedupeDB

    db = DedupeDB(config["db_path"])
    counts = asyncio.run(run_cycle(config, db, config["out_dir"]))
    print(f"\n✅ Cycle complete: {json.dumps(counts, indent=2)}")
    if config.get("blog_enabled", True):
        print(f"\n🌐 Blog updated → {config.get('blog_dir','blog')}/index.html")
    db.close()


def cmd_daemon(args, config: dict) -> None:
    """Run the 24×7 daemon."""
    if getattr(args, "live", False):
        config["live_mode"] = True
    if getattr(args, "depth", None):
        config["caption_depth"] = args.depth
        config["image_depth"]   = args.depth

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


def cmd_blog(args, config: dict) -> None:
    """Build / rebuild the static blog site."""
    from publisher.blog_publisher import publish as blog_publish
    clean = getattr(args, "clean", False) or config.get("blog_clean_rebuild", False)
    blog_dir = config.get("blog_dir", "blog")
    print(f"\n🏗  Building static blog → {blog_dir}/")
    n = blog_publish(
        out_dir=config["out_dir"],
        blog_dir=blog_dir,
        clean=clean,
    )
    print(f"✅ Blog published: {n} posts")
    print(f"   Open: {blog_dir}/index.html")
    print(f"   Deploy: push {blog_dir}/ to GitHub Pages / Netlify / any static host")


def cmd_status(args, config: dict) -> None:
    """Print DB stats and latest metrics."""
    from pipeline.dedupe import DedupeDB
    db = DedupeDB(config["db_path"])
    stats = db.stats()
    db.close()
    print("\n=== PhantomFeed — Status ===")
    print(f"DB: {config['db_path']}")
    for k, v in stats.items():
        print(f"  {k:20s}: {v}")
    sf = Path(config["status_file"])
    if sf.exists():
        print("\nLatest metrics (status.json):")
        print(sf.read_text())
    blog_dir = Path(config.get("blog_dir", "blog"))
    if blog_dir.exists():
        post_count = len(list((blog_dir / "posts").glob("*/index.html"))) if (blog_dir / "posts").exists() else 0
        print(f"\nBlog:  {blog_dir}/index.html  ({post_count} posts published)")


def cmd_reprocess(args, config: dict) -> None:
    from pipeline.dedupe import DedupeDB
    db = DedupeDB(config["db_path"])
    ok = db.delete(args.id)
    db.close()
    if ok:
        print(f"✅ Deleted {args.id!r} from DB. Run 'start' to reprocess.")
    else:
        print(f"⚠️  ID {args.id!r} not found in DB.")


def cmd_purge(args, config: dict) -> None:
    confirm = input("⚠️  This will delete ALL processed records. Type YES to confirm: ")
    if confirm.strip() != "YES":
        print("Aborted."); return
    from pipeline.dedupe import DedupeDB
    db = DedupeDB(config["db_path"])
    n = db.purge()
    db.close()
    print(f"✅ Purged {n} records from DB.")


# Seed items (kept from cli.py for test compatibility)
SEED_ITEMS = [
    {
        "title": "CVE-2026-1234 — Critical RCE in Apache HTTP Server 2.4",
        "description": (
            "A critical remote code execution vulnerability (CVSS 9.8) "
            "was disclosed in Apache HTTP Server 2.4.x allowing "
            "unauthenticated attackers to execute arbitrary code via "
            "a malformed HTTP/2 request header."
        ),
        "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-1234",
        "published_at": "2026-01-15T12:00:00Z",
        "source": "NVD-Seed",
    },
    {
        "title": "Massive Phishing Campaign Targets Indian Banks (2026)",
        "description": (
            "A large-scale phishing campaign impersonating major Indian "
            "banks was detected distributing credential-harvesting pages "
            "via WhatsApp and SMS. Over 50,000 victims reported."
        ),
        "url": "https://example.com/phishing-india-2026",
        "published_at": "2026-01-16T08:30:00Z",
        "source": "SecurityWeek-Seed",
    },
    {
        "title": "Ransomware Group Claims Healthcare Provider Breach",
        "description": (
            "The Clop ransomware group claimed responsibility for a "
            "breach affecting a major healthcare provider, reportedly "
            "exfiltrating 2 TB of patient records."
        ),
        "url": "https://example.com/ransomware-health-2026",
        "published_at": "2026-01-17T10:15:00Z",
        "source": "ThreatPost-Seed",
    },
]


def cmd_seed(args, config: dict) -> None:
    """Inject seed test items — also rebuilds blog after."""
    from core_v2 import process_item
    from pipeline import normalize
    from pipeline.dedupe import DedupeDB

    db = DedupeDB(config["db_path"])
    print(f"Seeding {len(SEED_ITEMS)} test items (depth={config.get('caption_depth','deep')})...")
    for raw in SEED_ITEMS:
        item = normalize(raw, fmt="rss")
        result = process_item(item, db, config, config["out_dir"])
        print(f"  [{result:10s}] {raw['title'][:60]}")
    db.close()
    print(f"\n✅ Seed complete. Check {config['out_dir']}/ for output.")
    # Rebuild blog
    if config.get("blog_enabled", True):
        cmd_blog(args, config)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="phantomfeed-v2",
        description="PhantomFeed v2 — Cybersecurity news → deep-analysis blog",
    )
    parser.add_argument("--config",   default="config.json")
    parser.add_argument("--loglevel", default=None)
    parser.add_argument("--live",     action="store_true", help="Enable live-only mode")
    parser.add_argument("--depth",    choices=["deep", "standard"], default=None,
                        help="Caption/image depth (default: deep)")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start",       help="Run one fetch cycle")
    sub.add_parser("daemon",      help="Run 24×7 daemon")
    sub.add_parser("status",      help="Show DB and metrics status")
    sub.add_parser("purge",       help="Purge all DB records")
    sub.add_parser("seed",        help="Inject seed test items")
    sub.add_parser("healthcheck", help="Start health-check HTTP server")

    blog_p = sub.add_parser("blog", help="Build/rebuild static blog website")
    blog_p.add_argument("--clean", action="store_true", help="Clean-rebuild blog")

    rp = sub.add_parser("reprocess", help="Force-reprocess a canonical ID")
    rp.add_argument("id", help="Canonical ID (e.g. cve:CVE-2026-1234)")

    args = parser.parse_args()
    config = _load_config(args.config)

    # CLI flag overrides
    if args.loglevel:
        config["log_level"] = args.loglevel
    if getattr(args, "live", False):
        config["live_mode"] = True
    if getattr(args, "depth", None):
        config["caption_depth"] = args.depth
        config["image_depth"]   = args.depth

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
