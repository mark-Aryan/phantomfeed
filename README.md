<!--
  PhantomFeed — README.md
  Copyright (c) 2026 Aryan Kumar Upadhyay (@aryankrupadhyay)
  Brand: codeXploit · https://codexploit.in
  Licensed under MIT — See LICENSE file for full terms.
-->

<div align="center">

```
  ██████╗ ██╗  ██╗ █████╗ ███╗  ██╗████████╗ ██████╗ ███╗   ███╗
  ██╔══██╗██║  ██║██╔══██╗████╗ ██║╚══██╔══╝██╔═══██╗████╗ ████║
  ██████╔╝███████║███████║██╔██╗██║   ██║   ██║   ██║██╔████╔██║
  ██╔═══╝ ██╔══██║██╔══██║██║╚████║   ██║   ██║   ██║██║╚██╔╝██║
  ██║     ██║  ██║██║  ██║██║ ╚███║   ██║   ╚██████╔╝██║ ╚═╝ ██║
  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝

              ███████╗███████╗███████╗██████╗
              ██╔════╝██╔════╝██╔════╝██╔══██╗
              █████╗  █████╗  █████╗  ██║  ██║
              ██╔══╝  ██╔══╝  ██╔══╝  ██║  ██║
              ██║     ███████╗███████╗██████╔╝
              ╚═╝     ╚══════╝╚══════╝╚═════╝
```

**Ghost in the machine. Signal in the noise.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-00d4ff?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-00dc78?style=flat-square)](LICENSE)
[![Powered by Claude](https://img.shields.io/badge/AI-Claude%20Haiku-blueviolet?style=flat-square&logo=anthropic&logoColor=white)](https://anthropic.com)
[![GitHub Pages](https://img.shields.io/badge/Deploy-GitHub%20Pages-222?style=flat-square&logo=github)](https://pages.github.com)
[![codeXploit](https://img.shields.io/badge/Brand-codeXploit-ff6600?style=flat-square)](https://codexploit.in)

**Automated 24×7 cybersecurity news → branded LinkedIn post generator**

*by **[Aryan Kumar Upadhyay](https://codexploit.in)** ([@aryankrupadhyay](https://twitter.com/aryankrupadhyay)) · [codeXploit](https://codexploit.in)*

---

[**Live Blog →**](https://mark-aryan.github.io/phantomfeed) · [**Quick Start**](#-quick-start) · [**CLI Reference**](#-cli-reference) · [**Config**](#-configuration-reference) · [**Deploy**](#-deployment)

</div>

---

## What Is PhantomFeed?

**PhantomFeed** is a production-grade, fully automated cybersecurity content engine. It continuously monitors the world's top security intelligence sources — NIST NVD, NewsAPI, and six elite RSS feeds — then transforms raw threat data into structured, SEO-optimized LinkedIn posts complete with branded images, published to a live static blog website in real time.

**No manual work. No outdated content. Just signal.**

```
┌─────────────────────────────────────────────────────────────────────┐
│  ╔══════════╗   ╔══════════╗   ╔══════════╗                        │
│  ║  NewsAPI ║   ║ NIST NVD ║   ║   RSS    ║   (3 live sources)     │
│  ╚═════╤════╝   ╚═════╤════╝   ╚═════╤════╝                        │
│        └──────────────┴──────────────┘                              │
│                        ▼                                            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Normalizer → Deduplicator → Classifier → Safety Filter     │   │
│  └─────────────────────────────┬───────────────────────────────┘   │
│                                ▼                                    │
│         ┌──────────────────────────────────┐                        │
│         │  Deep Caption + Branded Image     │                        │
│         │  (Claude AI or offline template)  │                        │
│         └──────────────┬───────────────────┘                        │
│                        ▼                                            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  out/  →  blog/  →  GitHub Pages  (auto-pushed, live site)  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

| Feature | Details |
|---|---|
| **3 live data sources** | NewsAPI, NIST NVD/CVE feed, 6 curated security RSS feeds |
| **Cursor-based live pulling** | Never re-fetches old news — true incremental streaming |
| **Deterministic deduplication** | SQLite-backed canonical IDs (CVE > URL > title hash) |
| **5-category classifier** | Vulnerability · Incident · Fraud · Bug · News |
| **18-rule safety filter** | Auto-quarantines PoC code, shellcode, and exploit walkthroughs |
| **Deep AI captions** | What happened · Why it matters · How to fix · How to prevent |
| **Two-panel branded images** | 1200×627 or 1080×1080, fully rendered offline (no external APIs) |
| **Static blog publisher** | Full website with search, category filters, RSS feed, JSON feed |
| **GitHub autopush** | Git Trees API — only uploads changed files (50× fewer API calls) |
| **Docker-ready** | Single-command 24×7 daemon deployment |

---

## 🚀 Quick Start

> **Zero API keys required** to generate your first posts.

```bash
# 1 — Clone
git clone https://github.com/mark-Aryan/phantomfeed
cd phantomfeed

# 2 — Install dependencies
pip install -r requirements.txt

# 3 — Generate sample posts instantly (no API keys needed)
python cli_v2.py seed

# 4 — View output
ls out/          # post directories: caption + image per item
ls blog/         # static website ready to deploy
```

**Expected output:**

```
╔════════════════════════════════════════════════╗
║  PhantomFeed v2 · wraith · codeXploit          ║
╚════════════════════════════════════════════════╝

▶  SEED MODE  —  injecting test items

  [generated  ] CVE-2026-1234 — Critical RCE in Apache HTTP Server 2.4
  [generated  ] Massive Phishing Campaign Targets Indian Banks (2026)
  [generated  ] Ransomware Group Claims Healthcare Provider Breach

✅ Seed complete → out/
✅ Blog built: 3 posts → blog/index.html
```

---

## 🔑 Free API Keys Setup

### NewsAPI — 100 requests/day free

```bash
# 1. Register: https://newsapi.org/register
# 2. Add to .env:
NEWSAPI_KEY=your_key_here
```

### NIST NVD — No key required

```bash
# Optional key for higher rate limits (50 req/30s vs 5 req/30s)
# Register: https://nvd.nist.gov/developers/request-an-api-key
NVD_API_KEY=your_key_here   # optional
```

### Claude AI — Richer, smarter captions

```bash
# 1. Get key: https://console.anthropic.com
# 2. Add to .env:
ANTHROPIC_API_KEY=sk-ant-...
# 3. Enable in config.json:
#    "caption_backend": "ai"
#    "ai_backend": "claude"
```

### GitHub — Auto-publish to GitHub Pages

```bash
# 1. Create a Personal Access Token with 'repo' scope
# 2. Add to .env:
GITHUB_TOKEN=ghp_your_token
GITHUB_REPO=your-username/your-repo
```

---

## 📁 Project Architecture

```
phantomfeed/
│
├── cli_v2.py                   # CLI entry point
├── core_v2.py                  # Orchestrator: run_cycle(), run_daemon()
├── banner.py                   # ASCII terminal banner
├── config.json                 # Full configuration
│
├── fetcher/                    # Async data ingestion (aiohttp + exponential backoff)
│   ├── newsapi_fetcher.py      # NewsAPI.org — cybersecurity keyword search
│   ├── nvd_fetcher.py          # NIST NVD — CVE feed, CVSS filtering
│   ├── rss_fetcher.py          # Multi-feed RSS (Krebs, THN, BleepingComputer…)
│   └── live_puller.py          # Cursor-based incremental fetcher (UPGRADE #2)
│
├── pipeline/                   # Data processing
│   ├── normalizer.py           # Canonical item format (strips HTML, parses dates)
│   ├── dedupe.py               # Canonical IDs + SQLite deduplication DB
│   ├── classifier.py           # Keyword → category (vulnerability/fraud/bug/…)
│   └── safety_filter.py        # 18-rule PoC/exploit detection + quarantine
│
├── generators/                 # Content generation
│   ├── deep_caption.py         # Deep AI + template caption engine (UPGRADE #1)
│   └── deep_image.py           # Two-panel PIL image renderer (UPGRADE #1)
│
├── publisher/                  # Output delivery
│   ├── blog_publisher.py       # Static site generator — blog/ (UPGRADE #3)
│   └── git_autopush.py         # GitHub Trees API publisher
│
├── brand/
│   └── brand_config.py         # SEO tokens from index.html
│
├── test_autopush.py            # End-to-end test suite
├── SAFETY.md                   # Explicit redaction policy
├── UPGRADE_README.md           # What's new in v2
└── docker-compose.yml          # Production container
```

---

## 🖥️ CLI Reference

```bash
# ── Single cycle (fetch → process → save → blog → push) ───────────────────
python cli_v2.py start
python cli_v2.py start --live          # live mode: only new items
python cli_v2.py start --depth deep    # deep captions (default)
python cli_v2.py start --depth standard # original short captions

# ── 24×7 daemon ──────────────────────────────────────────────────────────────
python cli_v2.py daemon
python cli_v2.py daemon --live         # recommended for production

# ── Blog only (rebuild from existing out/) ────────────────────────────────────
python cli_v2.py blog
python cli_v2.py blog --clean          # delete blog/ and rebuild from scratch

# ── Seed test items (no API keys needed) ──────────────────────────────────────
python cli_v2.py seed

# ── Operations ────────────────────────────────────────────────────────────────
python cli_v2.py status                # DB stats + last-run metrics
python cli_v2.py reprocess "cve:CVE-2026-1234"  # force re-generate one item
python cli_v2.py purge                 # delete all DB records (with confirmation)
python cli_v2.py healthcheck           # start HTTP health-check server on :8080

# ── Global flags ──────────────────────────────────────────────────────────────
python cli_v2.py --config /path/to/config.json daemon
python cli_v2.py --loglevel DEBUG daemon
```

---

## ⚙️ Configuration Reference

> All config lives in `config.json`. Environment variables always override file values.

```jsonc
{
  // ── Core ──────────────────────────────────────────────────────────────────
  "poll_interval":         3600,      // seconds between daemon cycles
  "db_path":               "data/dedupe.db",
  "out_dir":               "out",
  "log_level":             "INFO",

  // ── Data Sources ──────────────────────────────────────────────────────────
  "newsapi_key":           "",        // env: NEWSAPI_KEY
  "newsapi_page_size":     20,
  "nvd_enabled":           true,
  "nvd_api_key":           "",        // env: NVD_API_KEY (optional)
  "nvd_hours_back":        24,
  "nvd_min_cvss":          7.0,       // filter: only HIGH + CRITICAL CVEs
  "rss_enabled":           true,

  // ── Captions ──────────────────────────────────────────────────────────────
  "caption_backend":       "template",   // "template" | "ai"
  "caption_depth":         "deep",       // "deep" | "standard"
  "ai_backend":            "claude",     // "claude" | "huggingface"
  "claude_api_key":        "",           // env: ANTHROPIC_API_KEY
  "claude_model":          "claude-haiku-4-5-20251001",

  // ── Images ────────────────────────────────────────────────────────────────
  "image_backend":         "placeholder",  // "placeholder" | "remote"
  "image_depth":           "deep",         // "deep" | "standard"
  "image_size":            "linkedin",     // "linkedin" (1200x627) | "square" (1080x1080)

  // ── Live mode (Upgrade #2) ────────────────────────────────────────────────
  "live_mode":             true,        // only fetch items newer than last run
  "live_lookback_minutes": 90,          // first-run lookback window

  // ── Blog (Upgrade #3) ─────────────────────────────────────────────────────
  "blog_enabled":          true,
  "blog_dir":              "blog",
  "blog_clean_rebuild":    false,

  // ── GitHub auto-push ──────────────────────────────────────────────────────
  "autopush_enabled":      true,
  "autopush_mode":         "api",      // "api" (GitHub REST) | "git" (local git)
  "github_token":          "",         // env: GITHUB_TOKEN
  "github_repo":           "user/repo",// env: GITHUB_REPO
  "github_branch":         "gh-pages",

  // ── Quality ───────────────────────────────────────────────────────────────
  "similarity_threshold":  0.92        // Jaccard threshold for near-duplicate skip
}
```

---

## 🐳 Docker Deployment

```bash
# 1. Configure
cp config.json config.json   # edit with your API keys
cat > .env << EOF
NEWSAPI_KEY=your_key
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
GITHUB_REPO=your-username/phantomfeed
EOF

# 2. Build + run
docker-compose up -d

# 3. Monitor
docker-compose logs -f
curl http://localhost:8080/health

# 4. Stop
docker-compose down
```

The container automatically mounts `./out`, `./data`, `./logs`, and `./blog` for persistence across restarts.

---

## 🌐 Deployment Options

### GitHub Pages (Recommended — Free)

```bash
# Option A: Fully automatic (autopush in daemon)
# 1. Set GITHUB_TOKEN + GITHUB_REPO in .env
# 2. Set "autopush_enabled": true in config.json
# 3. python cli_v2.py daemon --live
# → Blog auto-pushes to gh-pages after every cycle with new posts

# Option B: Manual push
python cli_v2.py blog
git add blog/ && git commit -m "New posts" && git push origin gh-pages
```

Enable GitHub Pages: **Settings → Pages → Deploy from branch → gh-pages → /root**

Your site: `https://your-username.github.io/your-repo`

### Netlify (Instant, 30-second deploy)

```bash
python cli_v2.py blog
# Drag-and-drop blog/ at https://netlify.com/drop
```

### Cloudflare Pages

Connect your GitHub repo. Build command: `python cli_v2.py blog`. Publish directory: `blog`.

---

## 📂 Output Structure

```
out/
├── vulnerability/
│   └── 2026-03-15/
│       └── cve-2026-9999-critical-rce-a1b2c3/
│           ├── image.png        ← Branded image (1200×627)
│           ├── image_raw.png    ← Background without text
│           ├── post.txt         ← LinkedIn caption
│           └── meta.json        ← Metadata + canonical ID

blog/                            ← Static site (deploy this folder)
├── index.html                   ← Home feed (search + category filter)
├── posts/
│   └── cve-2026-9999-.../
│       ├── index.html           ← Individual post page
│       └── image.png
├── feed.json                    ← JSON feed (API consumers)
├── rss.xml                      ← RSS 2.0 feed
└── .nojekyll                    ← GitHub Pages marker
```

### Sample post.txt

```
🔴 [CRITICAL] CVE-2026-9999 — Critical RCE in Apache HTTP Server 2.4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔎 CVE Reference: CVE-2026-9999

📋 WHAT HAPPENED
A critical remote code execution vulnerability (CVSS 9.8) was disclosed
in Apache HTTP Server 2.4.x prior to 2.4.62. Unauthenticated attackers
can execute arbitrary OS commands via a specially crafted HTTP/2 frame.

⚡ WHY THIS MATTERS
Attackers can exploit this to gain unauthorized access, exfiltrate data,
or disrupt operations at massive scale across millions of Apache deployments.

🔧 HOW TO FIX (RIGHT NOW)
  ① Apply the vendor security patch immediately — check NVD advisory.
  ② If patch unavailable: restrict access via firewall / WAF rule.
  ③ Enable IDS/IPS signatures targeting this CVE pattern.

🛡️ HOW TO PREVENT (LONG-TERM)
  ◆ Maintain a real-time SBOM to detect vulnerable packages fast.
  ◇ Run weekly automated vulnerability scans (OpenVAS / Tenable).
  ▸ Subscribe to NVD feeds for zero-day alerts.
  ▹ Adopt patch SLA: Critical = 24h, High = 72h, Medium = 2 weeks.

#codeXploit #CVE #vulnerability #infosec #patchnow #OWASP

🔗 https://nvd.nist.gov/vuln/detail/CVE-2026-9999

— Aryan Kumar Upadhyay (@aryankrupadhyay) | codeXploit · codexploit.in
```

---

## 🔐 How Deduplication Works

```
Priority order for canonical IDs:

1. CVE ID in title/URL    →  "cve:CVE-2026-9999"        (global uniqueness)
2. URL hash (SHA-256)     →  "url:a1b2c3d4e5f6g7h8"     (article uniqueness)
3. title + time + source  →  "hash:deadbeef12345678"     (fallback)
```

**Near-duplicate guard:** Items with title Jaccard similarity > 0.92 but different URLs are treated as near-duplicates and silently skipped. Use `python cli_v2.py reprocess <id>` to force re-generation.

---

## 🛡️ Safety & Ethics

PhantomFeed includes a **18-rule automated safety filter** that quarantines any item containing:

- Fenced code blocks or `<code>` tags
- Shell prompt sequences or reverse shells
- `getshell`, `payload`, `PoC`, `proof-of-concept`
- Metasploit payload generation (`msfvenom`, `use exploit/`)
- Step-by-step exploit instructions or walkthroughs
- `curl | bash` or `wget | sh` pipe-to-shell patterns

Quarantined items receive a `review.txt` explanation. No caption or image is generated until a human runs `python cli_v2.py reprocess <id>` after manual review.

See [SAFETY.md](SAFETY.md) for the complete policy.

---

## 🧪 Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Unit + integration tests (no API keys needed)
python test_autopush.py

# Full end-to-end with GitHub push + live URL verification
GITHUB_TOKEN=ghp_xxx \
GITHUB_REPO=your-user/your-repo \
python test_autopush.py --verbose

# Skip live URL check (for CI without public network)
python test_autopush.py --skip-url-check

# With pytest (individual test classes)
pytest test_autopush.py::TestPipelineUnits -v
pytest test_autopush.py::TestBlogBuilder -v
pytest test_autopush.py::TestAutopush -v    # requires GITHUB_TOKEN
```

**Test coverage:**

| Test Class | Tests | Requires |
|---|---|---|
| `TestPipelineUnits` | 14 tests — canonical IDs, classifier, safety, normalizer, dedupe | Nothing |
| `TestPostGeneration` | 7 tests — real post generation in temp dir | Nothing |
| `TestBlogBuilder` | 10 tests — blog HTML, RSS, JSON feed validity | Nothing |
| `TestAutopush` | 6 tests — GitHub token, repo access, file upload verification | `GITHUB_TOKEN` |
| `TestDeployedSite` | 5 tests — live HTTP checks on deployed gh-pages URL | `GITHUB_REPO` |

---

## 🔍 SEO Caption Structure

All generated captions follow a strict SEO-optimized structure for LinkedIn:

```
1. Hook line     ← Threat level emoji + [LEVEL] badge + primary keyword front-loaded
2. CVE reference ← Precise identifier for searchability (when available)
3. What happened ← 3-4 sentences: technical specifics, affected versions
4. Why it matters← Impact analysis, blast radius, severity score
5. How to fix    ← 3 specific, numbered, immediately actionable steps
6. How to prevent← 4 proactive hardening recommendations with bullet icons
7. Hashtags      ← 4-6 tags always including #codeXploit + category terms
8. Source URL    ← Original attribution link
9. Author line   ← Aryan Kumar Upadhyay | codeXploit | codexploit.in
```

---

## 📡 RSS Sources (Pre-configured)

| Feed | Focus |
|---|---|
| [Krebs on Security](https://krebsonsecurity.com) | In-depth investigative reporting |
| [The Hacker News](https://thehackernews.com) | Breaking cybersecurity news |
| [Bleeping Computer](https://www.bleepingcomputer.com) | Malware, ransomware, vulnerabilities |
| [CISA Advisories](https://www.cisa.gov) | US government threat advisories |
| [SecurityWeek](https://www.securityweek.com) | Enterprise security intelligence |
| [Dark Reading](https://www.darkreading.com) | Threat research and analysis |

Add custom feeds in `config.json` under `"rss_feeds"`:

```json
"rss_feeds": [
  {"url": "https://your-feed.com/rss.xml", "name": "Your Feed Name"}
]
```

---

## 🧩 Extending PhantomFeed

### Add a new data source

```python
# fetcher/my_source.py
async def fetch(config: dict, session) -> list[dict]:
    # return list of raw dicts
    ...

# pipeline/normalizer.py — add case:
def normalize_my_source(item: dict) -> dict:
    return {"title": ..., "description": ..., "url": ..., ...}
```

### Add a new category

```python
# pipeline/classifier.py — append to RULES:
RULES.append((
    "supply_chain",
    [r"\bsupply chain\b", r"\bthird.party\b", r"\bdependency confusion\b"],
    1,
))
```

### Add a GPU image backend

```python
# generators/image_generator.py
def generate_diffusers(item, out_dir, config, size):
    from diffusers import StableDiffusionPipeline
    import torch
    pipe = StableDiffusionPipeline.from_pretrained(
        config.get("local_model_path", "runwayml/stable-diffusion-v1-5"),
        torch_dtype=torch.float16,
    ).to("cuda")
    # ... rest of generation
```

Set `"image_backend": "diffusers"` in config.json.

---

## 🖥️ Brand Tokens

Extracted automatically from `index.html` via `brand/brand_config.py`:

| Field | Value |
|---|---|
| Brand | codeXploit |
| Person | Aryan Kumar Upadhyay |
| Job Title | Cybersecurity Analyst & Ethical Hacker |
| Website | [codexploit.in](https://codexploit.in) |
| GitHub | [github.com/mark-Aryan](https://github.com/mark-Aryan) |
| LinkedIn | [linkedin.com/in/aryan-kumar-upadhyay](https://linkedin.com/in/aryan-kumar-upadhyay) |
| Twitter | [@aryankrupadhyay](https://twitter.com/aryankrupadhyay) |
| Fiverr | [fiverr.com/mark_aryan](https://fiverr.com/mark_aryan) |
| Primary Hashtag | #codeXploit |

---

## 📋 Requirements

```
Python       >= 3.10
aiohttp      >= 3.9
feedparser   >= 6.0
Pillow       >= 10.0
python-dotenv>= 1.0
```

Full dependency list in `requirements.txt`.

---

## 💡 Optimization Notes (v2 Production Fixes)

| Component | Problem | Fix Applied |
|---|---|---|
| `git_autopush.py` | Uploaded all 419 files every cycle → GitHub rate-limit kill | Git Trees API: one SHA comparison request, only upload changed files |
| `core_v2.py` | Blog re-published 200+ old posts even when 0 new items in live mode | Skip blog publish + autopush when `live_mode=True` and `fetched=0` |
| `core_v2.py` | `autopush()` was never called (missing from original) | Added at end of every cycle when `new_posts > 0` |
| `cli_v2.py` | `--live` flag only on parent parser, not subparsers → `unrecognized arguments` | Added `_add_run_flags()` applied to each subparser individually |
| `blog_publisher.py` | Slug collisions from posts with identical folder names | Unique slug = folder name + 6-char canonical_id suffix |
| `blog_publisher.py` | Missing `.nojekyll` → GitHub Pages ran Jekyll, mangled HTML | Always write `.nojekyll` first in `publish()` |

---

## ©️ Copyright & License

```
PhantomFeed v2
Copyright (c) 2026 Aryan Kumar Upadhyay

All rights reserved. This software and its associated branding,
visual design, content structures, and automation logic are the
exclusive intellectual property of Aryan Kumar Upadhyay trading as
codeXploit (https://codexploit.in).

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice, the author attribution line, and the
codeXploit brand identifiers MUST be retained in all copies or
substantial portions of the Software, including any generated content,
blog posts, images, and captions produced by the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

Brand: codeXploit · https://codexploit.in
Author: Aryan Kumar Upadhyay · @aryankrupadhyay
```

---

<div align="center">

**Made with 🔐 by [Aryan Kumar Upadhyay](https://codexploit.in)**

*Cybersecurity Analyst & Ethical Hacker · codeXploit · codexploit.in*

[![Twitter](https://img.shields.io/twitter/follow/aryankrupadhyay?style=social)](https://twitter.com/aryankrupadhyay)
[![GitHub](https://img.shields.io/github/followers/mark-Aryan?style=social)](https://github.com/mark-Aryan)

*© 2026 Aryan Kumar Upadhyay · MIT License · codeXploit*

</div>
