"""
publisher/blog_publisher.py
============================
UPGRADE #3 — Static Blog Publisher.

Reads the entire out/ directory and renders a fully self-contained
static blog website: HTML + CSS + JS, zero server needed.

Deploy to:
  • GitHub Pages  (push blog/ to gh-pages branch)
  • Netlify       (drag-drop blog/)
  • Cloudflare Pages, Vercel, Surge.sh, etc.
  • Any web server

Structure published:
  blog/
    index.html              ← Home feed (all posts, paginated)
    posts/<slug>/index.html ← Individual post page
    assets/
      style.css             ← Shared stylesheet
      app.js                ← Search, filter, theme toggle
    feed.json               ← JSON feed (for API consumers)
    rss.xml                 ← RSS feed

Features:
  • Cyberpunk dark theme matching codeXploit brand
  • Category filter + live search
  • Responsive (mobile-first)
  • Post image embedded as <img> (relative path)
  • Full in-depth caption rendered as structured HTML
  • Estimated read time
  • Social share buttons (LinkedIn, Twitter)
  • No external CDN dependencies (fully offline-capable)
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ─── Brand ────────────────────────────────────────────────────────────────────
try:
    from brand.brand_config import BRAND
except Exception:
    BRAND = {
        "brand_name": "codeXploit",
        "person_name": "Aryan Kumar Upadhyay",
        "website_url": "https://codexploit.in",
        "brand_hashtag": "#codeXploit",
        "watermark_text": "@aryankrupadhyay | codeXploit",
        "job_title": "Cybersecurity Analyst & Ethical Hacker",
    }

CATEGORY_EMOJI = {
    "vulnerability": "🔴",
    "incident": "🔥",
    "fraud": "🎣",
    "bug": "🐛",
    "news": "📰",
}

CATEGORY_COLOR = {
    "vulnerability": "#dc3232",
    "incident": "#ff8c00",
    "fraud": "#c800c8",
    "bug": "#ffc800",
    "news": "#00d4ff",
}

# ─── CSS ──────────────────────────────────────────────────────────────────────
SHARED_CSS = """
/* PhantomFeed Blog — codeXploit cyberpunk theme */
:root {
  --bg:       #05050f;
  --bg2:      #0d0d1e;
  --bg3:      #13132a;
  --cyan:     #00d4ff;
  --blue:     #004bcc;
  --lblue:    #1a6ef7;
  --text:     #e8eaf0;
  --muted:    #8892a4;
  --white:    #ffffff;
  --red:      #dc3232;
  --orange:   #ff8c00;
  --green:    #00dc78;
  --yellow:   #ffc800;
  --magenta:  #c800c8;
  --border:   #1e2240;
  --font-head: 'Courier New', 'Consolas', monospace;
  --font-body: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  --radius: 8px;
  --shadow: 0 4px 32px rgba(0,212,255,0.07);
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html { scroll-behavior: smooth; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 16px;
  line-height: 1.7;
  min-height: 100vh;
}

/* Scanline overlay */
body::before {
  content: '';
  position: fixed; inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(0,212,255,0.015) 2px, rgba(0,212,255,0.015) 4px
  );
  pointer-events: none; z-index: 9999;
}

a { color: var(--cyan); text-decoration: none; }
a:hover { text-decoration: underline; color: var(--lblue); }

/* ── Layout ─────────────────────────────────────── */
.site-header {
  background: linear-gradient(180deg, #000010 0%, var(--bg2) 100%);
  border-bottom: 2px solid var(--cyan);
  padding: 24px 0 0;
  position: sticky; top: 0; z-index: 100;
  box-shadow: 0 0 40px rgba(0,212,255,0.15);
}
.header-inner {
  max-width: 1200px; margin: 0 auto;
  padding: 0 24px;
  display: flex; align-items: center; gap: 16px;
  flex-wrap: wrap;
}
.logo {
  font-family: var(--font-head);
  font-size: 1.6rem; font-weight: bold;
  color: var(--cyan);
  text-shadow: 0 0 20px rgba(0,212,255,0.5);
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
.logo span { color: var(--white); }
.tagline {
  color: var(--muted); font-size: 0.8rem;
  font-family: var(--font-head);
  letter-spacing: 0.1em;
}
.header-search {
  margin-left: auto;
  display: flex; gap: 8px; align-items: center;
}
.search-input {
  background: var(--bg3); border: 1px solid var(--border);
  color: var(--text); padding: 8px 14px; border-radius: var(--radius);
  font-size: 0.9rem; width: 220px;
  transition: border-color 0.2s;
}
.search-input:focus {
  outline: none; border-color: var(--cyan);
  box-shadow: 0 0 8px rgba(0,212,255,0.2);
}
.cat-filters {
  display: flex; gap: 8px; padding: 14px 24px;
  max-width: 1200px; margin: 0 auto;
  overflow-x: auto; scrollbar-width: none;
}
.cat-btn {
  background: var(--bg3); border: 1px solid var(--border);
  color: var(--muted); padding: 5px 14px; border-radius: 20px;
  cursor: pointer; font-size: 0.82rem; white-space: nowrap;
  transition: all 0.2s; font-family: var(--font-body);
}
.cat-btn:hover, .cat-btn.active {
  border-color: var(--cyan); color: var(--cyan);
  background: rgba(0,212,255,0.08);
}

main {
  max-width: 1200px; margin: 0 auto;
  padding: 32px 24px;
}

/* ── Post grid ──────────────────────────────────── */
.posts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 24px;
}
.post-card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
  display: flex; flex-direction: column;
}
.post-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow);
  border-color: var(--cyan);
}
.post-card .card-img {
  width: 100%; aspect-ratio: 1200/627;
  object-fit: cover; display: block;
}
.post-card .card-img-placeholder {
  width: 100%; aspect-ratio: 1200/627;
  background: var(--bg3);
  display: flex; align-items: center; justify-content: center;
  font-size: 3rem;
}
.card-body { padding: 20px; flex: 1; display: flex; flex-direction: column; }
.card-meta {
  display: flex; gap: 8px; align-items: center;
  margin-bottom: 10px; flex-wrap: wrap;
}
.cat-badge {
  display: inline-block; padding: 3px 10px;
  border-radius: 4px; font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.05em; text-transform: uppercase;
}
.card-date { color: var(--muted); font-size: 0.78rem; }
.card-source { color: var(--muted); font-size: 0.78rem; }
.card-title {
  font-size: 1.05rem; font-weight: 700; color: var(--white);
  margin-bottom: 10px; line-height: 1.4;
}
.card-excerpt { color: var(--muted); font-size: 0.88rem; flex: 1; margin-bottom: 14px; }
.card-footer {
  display: flex; justify-content: space-between; align-items: center;
  border-top: 1px solid var(--border); padding-top: 12px; margin-top: auto;
}
.read-more {
  color: var(--cyan); font-size: 0.85rem; font-weight: 600;
}
.read-time { color: var(--muted); font-size: 0.78rem; }

/* ── Post page ──────────────────────────────────── */
.post-page { max-width: 820px; margin: 0 auto; padding: 40px 24px; }
.post-hero { width: 100%; border-radius: var(--radius); margin-bottom: 32px; }
.post-header { margin-bottom: 28px; }
.post-title {
  font-size: 2.1rem; font-weight: 800; color: var(--white);
  line-height: 1.25; margin-bottom: 16px;
  font-family: var(--font-head);
}
.post-meta { display: flex; gap: 14px; flex-wrap: wrap; color: var(--muted); font-size: 0.88rem; }
.post-meta a { color: var(--cyan); }

.post-body { font-size: 1rem; line-height: 1.9; color: var(--text); }
.post-body h2 {
  font-size: 1.25rem; color: var(--cyan);
  font-family: var(--font-head); margin: 32px 0 12px;
  border-left: 3px solid var(--cyan); padding-left: 12px;
}
.post-body h3 { font-size: 1.05rem; color: var(--lblue); margin: 24px 0 8px; }
.post-body p { margin-bottom: 16px; }
.post-body ul, .post-body ol { margin: 0 0 16px 24px; }
.post-body li { margin-bottom: 6px; }
.post-body a { color: var(--cyan); }
.post-body .threat-badge {
  display: inline-block; padding: 4px 14px;
  border-radius: 4px; font-weight: 700; font-size: 0.85rem;
  margin-bottom: 16px;
}

.fix-box, .prevent-box {
  background: var(--bg3); border-radius: var(--radius);
  padding: 20px 24px; margin: 24px 0;
}
.fix-box { border-left: 4px solid var(--green); }
.prevent-box { border-left: 4px solid var(--orange); }
.fix-box h2, .prevent-box h2 { border: none; padding: 0; margin-top: 0; }
.fix-box h2 { color: var(--green); }
.prevent-box h2 { color: var(--orange); }

.share-row {
  display: flex; gap: 12px; margin-top: 40px; flex-wrap: wrap;
}
.share-btn {
  padding: 10px 20px; border-radius: var(--radius); font-weight: 600;
  cursor: pointer; font-size: 0.9rem; border: none; transition: opacity 0.2s;
  text-decoration: none; display: inline-block;
}
.share-btn:hover { opacity: 0.85; text-decoration: none; }
.share-li { background: #0077b5; color: #fff; }
.share-tw { background: #1da1f2; color: #fff; }
.share-cp { background: var(--bg3); color: var(--cyan); border: 1px solid var(--cyan); }

/* ── Footer ─────────────────────────────────────── */
.site-footer {
  border-top: 1px solid var(--border);
  padding: 32px 24px; text-align: center;
  color: var(--muted); font-size: 0.85rem; margin-top: 60px;
}
.site-footer a { color: var(--cyan); }

/* ── Utilities ──────────────────────────────────── */
.hidden { display: none !important; }
.no-results {
  text-align: center; padding: 60px 20px;
  color: var(--muted); font-size: 1.1rem;
}
@media (max-width: 600px) {
  .posts-grid { grid-template-columns: 1fr; }
  .post-title { font-size: 1.5rem; }
  .search-input { width: 140px; }
}
"""

# ─── JS ───────────────────────────────────────────────────────────────────────
SHARED_JS = """
(function() {
  'use strict';

  // ── Category filter ──────────────────────────────────
  var activeCat = 'all';
  document.querySelectorAll('.cat-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.cat-btn').forEach(function(b){ b.classList.remove('active'); });
      btn.classList.add('active');
      activeCat = btn.dataset.cat || 'all';
      applyFilters();
    });
  });

  // ── Search ───────────────────────────────────────────
  var searchEl = document.getElementById('search-input');
  if (searchEl) {
    searchEl.addEventListener('input', applyFilters);
  }

  function applyFilters() {
    var query = searchEl ? searchEl.value.toLowerCase().trim() : '';
    var cards = document.querySelectorAll('.post-card');
    var visible = 0;
    cards.forEach(function(card) {
      var cat  = card.dataset.cat || '';
      var text = (card.dataset.title || '').toLowerCase();
      var catOk    = activeCat === 'all' || cat === activeCat;
      var searchOk = !query || text.indexOf(query) !== -1;
      if (catOk && searchOk) {
        card.classList.remove('hidden');
        visible++;
      } else {
        card.classList.add('hidden');
      }
    });
    var nr = document.getElementById('no-results');
    if (nr) nr.classList.toggle('hidden', visible > 0);
  }

  // ── Copy share ───────────────────────────────────────
  document.querySelectorAll('.share-cp').forEach(function(btn) {
    btn.addEventListener('click', function() {
      navigator.clipboard.writeText(window.location.href).then(function() {
        btn.textContent = '✓ Copied!';
        setTimeout(function(){ btn.textContent = '🔗 Copy Link'; }, 2000);
      });
    });
  });

  // ── Fade-in cards ─────────────────────────────────────
  var cards2 = document.querySelectorAll('.post-card');
  cards2.forEach(function(c, i) {
    c.style.opacity = '0';
    c.style.transform = 'translateY(20px)';
    c.style.transition = 'opacity 0.4s ease ' + (i * 0.04) + 's, transform 0.4s ease ' + (i * 0.04) + 's';
    setTimeout(function(){ c.style.opacity = '1'; c.style.transform = ''; }, 80 + i * 40);
  });
})();
"""

# ─── HTML helpers ─────────────────────────────────────────────────────────────

def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _cat_badge_html(cat: str) -> str:
    color = CATEGORY_COLOR.get(cat, "#00d4ff")
    emoji = CATEGORY_EMOJI.get(cat, "📰")
    return (
        f'<span class="cat-badge" style="background:{color}22;color:{color};'
        f'border:1px solid {color}44;">{emoji} {cat.upper()}</span>'
    )


def _caption_to_html(caption: str) -> str:
    """
    Convert plain-text deep caption to structured HTML.
    Recognises section headers like 📋 WHAT HAPPENED, 🔧 HOW TO FIX, etc.
    """
    lines = caption.split("\n")
    html_parts: list[str] = []
    in_fix = in_prevent = False

    SECTION_ICONS = {
        "WHAT HAPPENED":   ("h2", "📋 WHAT HAPPENED", ""),
        "WHY THIS MATTERS":("h2", "⚡ WHY THIS MATTERS", ""),
        "HOW TO FIX":      ("fix-h2", "🔧 HOW TO FIX (RIGHT NOW)", "fix-box"),
        "HOW TO PREVENT":  ("prev-h2", "🛡️ HOW TO PREVENT", "prevent-box"),
    }

    i = 0
    open_box = ""
    while i < len(lines):
        line = lines[i].strip()

        # Close open box when we hit a new section or end
        def _close_box():
            nonlocal open_box
            if open_box:
                html_parts.append("</div>")
                open_box = ""

        # Section detection
        matched_section = False
        for key, (tag, label, box_cls) in SECTION_ICONS.items():
            if key in line.upper():
                _close_box()
                if box_cls:
                    html_parts.append(f'<div class="{box_cls}">')
                    open_box = box_cls
                html_parts.append(f"<h2>{label}</h2>")
                matched_section = True
                break

        if not matched_section:
            if line.startswith("━") or line.startswith("─"):
                i += 1; continue
            elif line.startswith("#"):
                tags = re.findall(r"#\w+", line)
                html_parts.append(
                    '<p class="hashtags" style="color:var(--cyan);margin:20px 0;">'
                    + " ".join(f'<span style="margin-right:6px">{t}</span>' for t in tags)
                    + "</p>"
                )
            elif re.match(r"^[①②③④⑤]", line) or re.match(r"^[◆◇▸▹▪]", line):
                html_parts.append(f"<li>{_html_escape(line[1:].strip())}</li>")
            elif line.startswith("🔗"):
                url_m = re.search(r"https?://\S+", line)
                if url_m:
                    u = url_m.group(0)
                    html_parts.append(
                        f'<p>🔗 <a href="{_html_escape(u)}" target="_blank" rel="noopener">'
                        f'{_html_escape(u)}</a></p>'
                    )
            elif line.startswith("—") or "Aryan Kumar Upadhyay" in line or "codexploit.in" in line:
                html_parts.append(
                    f'<p style="color:var(--muted);font-size:0.9rem;margin-top:16px;">'
                    f'{_html_escape(line)}</p>'
                )
            elif line:
                html_parts.append(f"<p>{_html_escape(line)}</p>")

        i += 1

    if open_box:
        html_parts.append("</div>")

    return "\n".join(html_parts)


def _read_time(text: str) -> int:
    words = len(text.split())
    return max(1, round(words / 200))


# ─── Load post data from out/ ─────────────────────────────────────────────────

def _load_posts(out_dir: Path) -> list[dict]:
    """Walk out/ directory and collect all post data."""
    posts = []
    for meta_file in sorted(out_dir.rglob("meta.json"), reverse=True):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        post_dir = meta_file.parent
        caption = ""
        post_txt = post_dir / "post.txt"
        if post_txt.exists():
            caption = post_txt.read_text(encoding="utf-8", errors="replace")

        image = None
        for img_name in ("image.png", "image_raw.png"):
            if (post_dir / img_name).exists():
                image = img_name
                break

        review_txt = post_dir / "review.txt"
        is_flagged = review_txt.exists()

        posts.append({
            "meta":     meta,
            "caption":  caption,
            "image":    image,
            "dir":      post_dir,
            "flagged":  is_flagged,
            "slug":     meta.get("slug", post_dir.name),
            "title":    meta.get("title", "Untitled"),
            "category": meta.get("category", "news"),
            "source":   meta.get("source", ""),
            "url":      meta.get("url", ""),
            "pub":      meta.get("published_at", ""),
            "cid":      meta.get("canonical_id", ""),
            "read_time": _read_time(caption),
        })

    return posts


# ─── Page generators ──────────────────────────────────────────────────────────

def _site_header_html(root_prefix: str = "") -> str:
    cats = ["all", "vulnerability", "incident", "fraud", "bug", "news"]
    cat_btns = "".join(
        f'<button class="cat-btn{"  active" if c=="all" else ""}" data-cat="{c}">'
        f'{"📋 All" if c=="all" else CATEGORY_EMOJI.get(c,"")+" "+c.title()}'
        f"</button>"
        for c in cats
    )
    return f"""
<header class="site-header">
  <div class="header-inner">
    <div>
      <div class="logo">Phantom<span>Feed</span></div>
      <div class="tagline">Ghost in the machine. Signal in the noise.</div>
    </div>
    <div class="header-search">
      <input id="search-input" class="search-input" type="search"
             placeholder="Search posts…" aria-label="Search posts">
    </div>
  </div>
  <div class="cat-filters">{cat_btns}</div>
</header>"""


def _site_footer_html() -> str:
    year = datetime.now().year
    return f"""
<footer class="site-footer">
  <p>
    © {year} <a href="{BRAND.get('website_url','#')}" target="_blank">{BRAND['brand_name']}</a>
    · {BRAND['person_name']} · {BRAND.get('job_title','')}
  </p>
  <p style="margin-top:6px;color:#444;">
    Automated cybersecurity news · Powered by PhantomFeed
  </p>
</footer>"""


def _page_wrap(title: str, body: str, root_prefix: str = "", extra_style: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{_html_escape(title)} · PhantomFeed</title>
  <meta name="description" content="Cybersecurity news by {BRAND['brand_name']}">
  <style>{SHARED_CSS}{extra_style}</style>
</head>
<body>
{_site_header_html(root_prefix)}
{body}
{_site_footer_html()}
<script>{SHARED_JS}</script>
</body>
</html>"""


def _build_index(posts: list[dict], blog_dir: Path) -> None:
    """Generate index.html with post grid."""
    cards_html = ""
    for p in posts:
        if p["flagged"]:
            continue   # never publish flagged posts
        cat   = p["category"]
        color = CATEGORY_COLOR.get(cat, "#00d4ff")
        # Relative image path (image is in posts/<slug>/)
        img_tag = ""
        if p["image"]:
            img_tag = (
                f'<img class="card-img" src="posts/{p["slug"]}/{p["image"]}" '
                f'alt="{_html_escape(p["title"])}" loading="lazy">'
            )
        else:
            img_tag = (
                f'<div class="card-img-placeholder">'
                f'{CATEGORY_EMOJI.get(cat, "📰")}</div>'
            )

        excerpt = p["caption"][:200].replace("\n", " ").strip() + "…" if p["caption"] else ""

        pub_display = ""
        try:
            dt = datetime.fromisoformat(p["pub"].replace("Z", "+00:00"))
            pub_display = dt.strftime("%b %d, %Y")
        except Exception:
            pub_display = p["pub"][:10]

        cards_html += f"""
<article class="post-card" data-cat="{cat}" data-title="{_html_escape(p['title'])}">
  <a href="posts/{p['slug']}/index.html">{img_tag}</a>
  <div class="card-body">
    <div class="card-meta">
      {_cat_badge_html(cat)}
      <span class="card-date">{pub_display}</span>
      <span class="card-source">{_html_escape(p['source'])}</span>
    </div>
    <h2 class="card-title">
      <a href="posts/{p['slug']}/index.html">{_html_escape(p['title'])}</a>
    </h2>
    <p class="card-excerpt">{_html_escape(excerpt)}</p>
    <div class="card-footer">
      <a class="read-more" href="posts/{p['slug']}/index.html">Read more →</a>
      <span class="read-time">⏱ {p['read_time']} min read</span>
    </div>
  </div>
</article>"""

    body = f"""
<main>
  <div class="posts-grid" id="posts-grid">
    {cards_html}
  </div>
  <p class="no-results hidden" id="no-results">No posts match your search.</p>
</main>"""

    html = _page_wrap("Home", body, root_prefix="")
    (blog_dir / "index.html").write_text(html, encoding="utf-8")
    log.info("Generated index.html (%d posts)", sum(1 for p in posts if not p["flagged"]))


def _build_post_page(p: dict, blog_dir: Path) -> None:
    """Generate individual post HTML page."""
    if p["flagged"]:
        return

    post_slug = p["slug"]
    post_out  = blog_dir / "posts" / post_slug
    post_out.mkdir(parents=True, exist_ok=True)

    # Copy image
    img_html = ""
    if p["image"]:
        src = p["dir"] / p["image"]
        dst = post_out / p["image"]
        if src.exists():
            shutil.copy2(src, dst)
        img_html = (
            f'<img class="post-hero" src="{p["image"]}" '
            f'alt="{_html_escape(p["title"])}">'
        )

    # Dates
    pub_display = ""
    try:
        dt = datetime.fromisoformat(p["pub"].replace("Z", "+00:00"))
        pub_display = dt.strftime("%B %d, %Y · %H:%M UTC")
    except Exception:
        pub_display = p["pub"][:19]

    cat   = p["category"]
    color = CATEGORY_COLOR.get(cat, "#00d4ff")
    caption_html = _caption_to_html(p["caption"])

    # Social share
    share_url   = f"posts/{post_slug}/index.html"
    title_enc   = _html_escape(p["title"])
    li_url  = f"https://www.linkedin.com/shareArticle?mini=true&url={share_url}&title={title_enc}"
    tw_url  = f"https://twitter.com/intent/tweet?text={title_enc}&url={share_url}"

    source_link = ""
    if p["url"]:
        source_link = (
            f'· <a href="{_html_escape(p["url"])}" target="_blank" rel="noopener">'
            f'Original Source ↗</a>'
        )

    body = f"""
<article class="post-page">
  {img_html}
  <header class="post-header">
    {_cat_badge_html(cat)}
    <h1 class="post-title">{_html_escape(p["title"])}</h1>
    <div class="post-meta">
      <span>📅 {pub_display}</span>
      <span>🗞 {_html_escape(p['source'])}</span>
      <span>⏱ {p['read_time']} min read</span>
      {source_link}
    </div>
  </header>
  <section class="post-body">
    {caption_html}
  </section>
  <div class="share-row">
    <a class="share-btn share-li" href="{li_url}" target="_blank" rel="noopener">
      🔗 Share on LinkedIn
    </a>
    <a class="share-btn share-tw" href="{tw_url}" target="_blank" rel="noopener">
      🐦 Share on Twitter
    </a>
    <button class="share-btn share-cp">🔗 Copy Link</button>
  </div>
  <p style="margin-top:32px;">
    <a href="../../index.html">← Back to all posts</a>
  </p>
</article>"""

    html = _page_wrap(p["title"], body, root_prefix="../../")
    (post_out / "index.html").write_text(html, encoding="utf-8")


def _build_json_feed(posts: list[dict], blog_dir: Path) -> None:
    """Generate a JSON feed for programmatic consumers."""
    items = []
    for p in posts:
        if p["flagged"]:
            continue
        items.append({
            "id":         p["cid"],
            "title":      p["title"],
            "category":   p["category"],
            "source":     p["source"],
            "url":        p["url"],
            "published":  p["pub"],
            "post_url":   f"posts/{p['slug']}/index.html",
            "image":      f"posts/{p['slug']}/{p['image']}" if p["image"] else None,
            "excerpt":    p["caption"][:280].replace("\n", " "),
        })
    feed = {
        "version": "1.1",
        "title":   "PhantomFeed — codeXploit Cybersecurity Blog",
        "home_page_url": BRAND.get("website_url", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }
    (blog_dir / "feed.json").write_text(
        json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _build_rss(posts: list[dict], blog_dir: Path) -> None:
    """Generate RSS 2.0 XML."""
    items_xml = ""
    for p in posts[:50]:    # cap RSS at 50 most recent
        if p["flagged"]:
            continue
        pub_rfc = ""
        try:
            from email.utils import format_datetime
            dt = datetime.fromisoformat(p["pub"].replace("Z", "+00:00"))
            pub_rfc = format_datetime(dt)
        except Exception:
            pub_rfc = p["pub"]

        items_xml += f"""
  <item>
    <title><![CDATA[{p["title"]}]]></title>
    <link>posts/{p["slug"]}/index.html</link>
    <guid isPermaLink="false">{_html_escape(p["cid"])}</guid>
    <pubDate>{pub_rfc}</pubDate>
    <category>{_html_escape(p["category"])}</category>
    <description><![CDATA[{p["caption"][:400]}]]></description>
  </item>"""

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>PhantomFeed — {BRAND['brand_name']} Cybersecurity</title>
    <link>{BRAND.get('website_url','')}</link>
    <description>Automated cybersecurity news by {BRAND['person_name']}</description>
    <language>en</language>
    {items_xml}
  </channel>
</rss>"""
    (blog_dir / "rss.xml").write_text(rss, encoding="utf-8")


# ─── Public entry point ────────────────────────────────────────────────────────

def publish(
    out_dir:  str | Path = "out",
    blog_dir: str | Path = "blog",
    clean:    bool = False,
) -> int:
    """
    Build the static blog from out_dir into blog_dir.

    Args:
        out_dir:  PhantomFeed output directory
        blog_dir: destination for static site
        clean:    if True, delete blog_dir before rebuilding

    Returns:
        Number of posts published
    """
    out_dir  = Path(out_dir)
    blog_dir = Path(blog_dir)

    if clean and blog_dir.exists():
        shutil.rmtree(blog_dir)
        log.info("Cleaned blog dir: %s", blog_dir)

    blog_dir.mkdir(parents=True, exist_ok=True)
    (blog_dir / "posts").mkdir(exist_ok=True)

    posts = _load_posts(out_dir)
    log.info("Loaded %d posts from %s", len(posts), out_dir)

    _build_index(posts, blog_dir)
    for p in posts:
        _build_post_page(p, blog_dir)
    _build_json_feed(posts, blog_dir)
    _build_rss(posts, blog_dir)

    published = sum(1 for p in posts if not p["flagged"])
    log.info("Blog published: %d posts → %s", published, blog_dir)
    return published
