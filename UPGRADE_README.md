# PhantomFeed v2 — Upgrade Guide

> **All original code preserved. Three new modules added on top.**

---

## What's New

### Upgrade 1 — In-Depth Captions & Two-Panel Images

**Files added:**
- `generators/deep_caption.py`
- `generators/deep_image.py`

**What changed:**

Every generated post now contains a full analysis structure:

```
🔴 [CRITICAL] CVE-2026-1234 — RCE in Apache
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔎 CVE Reference: CVE-2026-1234

📋 WHAT HAPPENED
Detailed 3-4 sentence technical explanation of the vulnerability,
its mechanism, and what versions/systems are affected.

⚡ WHY THIS MATTERS
Impact analysis — what attackers can do, blast radius, severity.

🔧 HOW TO FIX (RIGHT NOW)
  ① Apply the vendor security patch immediately.
  ② If patch unavailable: restrict access via WAF rule.
  ③ Enable IDS/IPS signatures targeting this CVE.

🛡️ HOW TO PREVENT (LONG-TERM)
  ◆ Maintain a real-time SBOM to detect vulnerable packages fast.
  ◇ Run weekly automated vulnerability scans.
  ▸ Subscribe to NVD feeds for zero-day alerts.
  ▹ Adopt a patch SLA: Critical = 24h, High = 72h.

#codeXploit #CVE #vulnerability #infosec #patchnow #OWASP

🔗 https://nvd.nist.gov/vuln/detail/CVE-2026-1234

— Aryan Kumar Upadhyay (@aryankrupadhyay) | codeXploit
```

**Image:** Two-panel layout:
- **Left** — Title, threat level badge (🔴 CRITICAL), category badge, CVE ID
- **Right** — HOW TO FIX (3 steps) + HOW TO PREVENT (4 bullets)

**Config keys:**
```json
"caption_depth": "deep",    // "deep" | "standard" (original)
"image_depth":   "deep"     // "deep" | "standard" (original)
```

**CLI:**
```bash
python cli_v2.py start --depth deep      # default
python cli_v2.py start --depth standard  # use original short captions
```

---

### Upgrade 2 — Live-Only News Puller

**File added:** `fetcher/live_puller.py`

**Problem solved:** Original fetchers fetched last 24 hours of NVD + all RSS
on every run, causing hundreds of duplicates and wasting API quota.

**How it works:**
- Stores a **cursor** (high-water timestamp) per source in `data/dedupe.db`
- Each run fetches **only items newer than the cursor**
- First run looks back `live_lookback_minutes` (default: 90 min)
- Cursors auto-advance to newest item seen each run
- **True zero duplicate fetching** — never refetches old news

```
Run 1 (first ever):  fetches last 90 min  → cursor = now
Run 2 (1h later):    fetches last 1 hour  → cursor = now
Run 3 (3h later):    fetches last 3 hours → cursor = now
```

**Config keys:**
```json
"live_mode": true,              // enable live-only pulling
"live_lookback_minutes": 90     // first-run lookback window
```

**CLI:**
```bash
python cli_v2.py start --live       # one live cycle
python cli_v2.py daemon --live      # 24×7 live daemon
```

**Or set in config:**
```json
"live_mode": true
```

---

### Upgrade 3 — Static Blog Publisher

**File added:** `publisher/blog_publisher.py`

**What it does:**  
After every cycle, reads the entire `out/` directory and renders a
complete, self-contained static blog website in `blog/`.

```
blog/
  index.html              ← Home feed (all posts, search + filter)
  posts/
    cve-2026-1234-.../
      index.html          ← Full individual post page
      image.png           ← Post image (copied from out/)
    phishing-campaign-.../
      index.html
      image.png
  feed.json               ← JSON feed (API consumers)
  rss.xml                 ← RSS 2.0 feed
  .nojekyll               ← GitHub Pages marker
```

**Features:**
- Cyberpunk dark theme (codeXploit brand colors)
- Live search bar (client-side JS, no backend needed)
- Category filter tabs (Vulnerability / Incident / Fraud / Bug / News)
- Deep caption rendered as structured HTML with FIX/PREVENT boxes
- LinkedIn + Twitter share buttons on every post
- Responsive (mobile-first)
- Zero external CDN dependencies
- JSON feed + RSS feed

**Config keys:**
```json
"blog_enabled": true,        // rebuild blog after every cycle
"blog_dir": "blog",          // output folder (deploy this)
"blog_clean_rebuild": false  // true = wipe blog/ before rebuild
```

**CLI:**
```bash
python cli_v2.py blog           # build blog from current out/
python cli_v2.py blog --clean   # clean rebuild
```

---

## Deployment (Upgrade 3)

### GitHub Pages (Free, Unlimited Storage)

```bash
# 1. Push your repo to GitHub
git init && git remote add origin https://github.com/YOUR/REPO

# 2. Enable GitHub Actions:
#    Copy .github/workflows/deploy-blog.yml into your repo

# 3. Set up GitHub Pages:
#    Settings → Pages → Source: Deploy from branch → gh-pages

# 4. Every time you push new out/ content, blog auto-deploys
#    URL: https://YOUR_USERNAME.github.io/REPO_NAME/

# Manual trigger
python cli_v2.py blog
git add blog/ out/
git commit -m "New cybersec posts"
git push origin main
# GitHub Actions rebuilds and deploys automatically
```

### Netlify Drop (Instant, Free)
```bash
python cli_v2.py blog
# Go to netlify.com/drop
# Drag the blog/ folder into the browser
# Done — live URL in 30 seconds
```

### Surge.sh (Free, Custom Domain)
```bash
npm install -g surge
python cli_v2.py blog
cd blog && surge . YOUR_DOMAIN.surge.sh
```

### Cloudflare Pages
```bash
# Connect GitHub repo to Cloudflare Pages
# Build command: python cli_v2.py blog
# Publish directory: blog
# Auto-deploys on every git push
```

---

## Quick Start (v2)

```bash
# Install (same as before, no new deps needed)
pip install -r requirements.txt

# Test seed with deep captions + blog
python cli_v2.py seed

# Live daemon with blog auto-publish
python cli_v2.py daemon --live

# Just rebuild the blog from existing out/
python cli_v2.py blog

# Standard (original) mode — no changes to behaviour
python cli_v2.py start --depth standard
```

---

## Backward Compatibility

| What | Status |
|---|---|
| `cli.py` | ✅ Unchanged — still works |
| `core.py` | ✅ Unchanged — still works |
| `config.json` | ✅ All old keys respected |
| `out/` structure | ✅ Identical — new files are additive |
| `data/dedupe.db` | ✅ Identical schema + new `live_cursors` table |
| All tests | ✅ Pass unchanged |
| Old captions | ✅ `--depth standard` restores original behaviour |

**To use the upgrade:** replace `python cli.py` with `python cli_v2.py`. That's it.

---

## File Map

```
NEW FILES (additions only, nothing modified):
├── generators/
│   ├── deep_caption.py      ← Upgrade 1: in-depth caption engine
│   └── deep_image.py        ← Upgrade 1: two-panel image renderer
├── fetcher/
│   └── live_puller.py       ← Upgrade 2: cursor-based live fetcher
├── publisher/
│   └── blog_publisher.py    ← Upgrade 3: static blog site generator
├── core_v2.py               ← Upgraded orchestrator (uses all 3)
├── cli_v2.py                ← Upgraded CLI (adds blog + --live + --depth)
├── config_v2.json           ← Annotated config with all new keys
└── .github/
    └── workflows/
        └── deploy-blog.yml  ← Auto-deploy to GitHub Pages
```
