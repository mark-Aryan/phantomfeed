#!/usr/bin/env python3
"""
seed_demo.py
============
Demo seed runner that doesn't require aiohttp/feedparser.
Processes 3 sample items through the full pipeline and shows output.
"""
import sys, types, json
from pathlib import Path

# Mock unavailable packages
for mod_name in ['aiohttp', 'feedparser']:
    m = types.ModuleType(mod_name)
    if mod_name == 'aiohttp':
        m.ClientSession = object; m.ClientError = Exception
        m.TCPConnector = object; m.ClientTimeout = object
    sys.modules[mod_name] = m

dotenv_mod = types.ModuleType('dotenv')
dotenv_mod.load_dotenv = lambda: None
sys.modules['dotenv'] = dotenv_mod

sys.path.insert(0, '.')

from pipeline.dedupe import DedupeDB, canonical_id, slugify
from pipeline.normalizer import normalize_rss
from pipeline.classifier import classify
from pipeline.safety_filter import check, review_text
from generators.text_generator import generate_template
from generators.image_generator import generate_placeholder
from storage.organiser import item_dir, save_post, save_meta, save_review, copy_images

SEED_ITEMS = [
    {
        "title": "CVE-2026-1234 — Critical RCE in Apache HTTP Server 2.4",
        "summary": (
            "A critical remote code execution vulnerability (CVSS 9.8) "
            "was disclosed in Apache HTTP Server 2.4.x allowing "
            "unauthenticated attackers to execute arbitrary code via "
            "a malformed HTTP/2 request header."
        ),
        "link": "https://nvd.nist.gov/vuln/detail/CVE-2026-1234",
        "published": "Wed, 15 Jan 2026 12:00:00 +0000",
        "_feed_name": "NVD-Seed",
    },
    {
        "title": "Massive Phishing Campaign Targets Indian Banks (2026)",
        "summary": (
            "A large-scale phishing campaign impersonating major Indian "
            "banks was detected distributing credential-harvesting pages "
            "via WhatsApp and SMS. Over 50,000 victims reported."
        ),
        "link": "https://example-sec.com/phishing-india-2026",
        "published": "Thu, 16 Jan 2026 08:30:00 +0000",
        "_feed_name": "SecurityWeek-Seed",
    },
    {
        "title": "Ransomware Group Claims Healthcare Provider Data Breach",
        "summary": (
            "The Clop ransomware group claimed responsibility for a "
            "breach affecting a major healthcare provider, reportedly "
            "exfiltrating 2 TB of patient records."
        ),
        "link": "https://example-sec.com/ransomware-health-2026",
        "published": "Fri, 17 Jan 2026 10:15:00 +0000",
        "_feed_name": "ThreatPost-Seed",
    },
]

OUT_DIR = Path("out")
DB_PATH = Path("data/dedupe.db")

def process(raw, db, config):
    item = normalize_rss(raw)
    item["category"] = classify(item["title"], item.get("description",""))

    title = item.get("title","")
    url   = item.get("url","")
    pub   = item.get("published_at","")
    src   = item.get("source","")

    cid = canonical_id(title=title, url=url, published_at=pub, source=src)

    if db.is_processed(cid):
        return "dupe", cid

    safety = check(item)
    out = item_dir(OUT_DIR, item, cid)

    if not safety.is_safe:
        save_review(out, review_text(item, safety.reasons))
        save_meta(out, item, cid)
        db.mark_processed(canonical_id=cid, slug=slugify(title),
                          category=item["category"], source=src,
                          url=url, title=title, published_at=pub, flagged=True)
        return "flagged", cid

    caption = generate_template(item)
    raw_p, fin_p = generate_placeholder(item, out)
    save_post(out, caption, item)
    save_meta(out, item, cid)
    copy_images(out, raw_p, fin_p)
    db.mark_processed(canonical_id=cid, slug=slugify(title),
                      category=item["category"], source=src,
                      url=url, title=title, published_at=pub, flagged=False)
    return "generated", cid

if __name__ == "__main__":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db = DedupeDB(DB_PATH)
    config = {}

    print("\n=== codeXploit Cyber News Poster — Seed Demo ===\n")
    for raw in SEED_ITEMS:
        status, cid = process(raw, db, config)
        print("  [%-10s] %s" % (status, raw["title"][:60]))

    print("\n--- Second run (demonstrates deduplication) ---")
    for raw in SEED_ITEMS:
        status, cid = process(raw, db, config)
        print("  [%-10s] %s" % (status, raw["title"][:60]))

    db.close()

    print("\n\n=== Output Structure ===")
    for f in sorted(OUT_DIR.rglob("*"))[:30]:
        if f.is_file():
            print(" ", f.relative_to(OUT_DIR))

    # Show sample caption
    post_files = list(OUT_DIR.rglob("post.txt"))
    if post_files:
        print("\n\n=== Sample post.txt ===\n")
        print(post_files[0].read_text())
