"""
generators/deep_image.py
=========================
UPGRADE #1 — Deep image generator.

Creates a two-panel LinkedIn image:
  LEFT  panel  — Title + threat level + CVE badge + category accent
  RIGHT panel  — Fix steps (HOW TO FIX) + Prevent steps (HOW TO PREVENT)

Falls back to original placeholder generator on any error.
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
from pathlib import Path
from typing import Any

from brand.brand_config import BRAND

log = logging.getLogger(__name__)

LINKEDIN_W, LINKEDIN_H = 1200, 627
SQUARE_W,  SQUARE_H   = 1080, 1080

PALETTE = {
    "bg_dark":  (5, 5, 15),
    "bg_card":  (13, 13, 30),
    "bg_panel": (10, 10, 25),
    "cyan":     (0, 212, 255),
    "blue":     (0, 75, 204),
    "text":     (232, 234, 240),
    "muted":    (136, 146, 164),
    "white":    (255, 255, 255),
    "green":    (0, 220, 120),
    "orange":   (255, 140, 0),
    "red":      (220, 50, 50),
    "yellow":   (255, 200, 0),
    "divider":  (30, 35, 60),
}

CATEGORY_ACCENT = {
    "vulnerability": (220, 50,  50),
    "incident":      (255, 140,  0),
    "fraud":         (200,  0, 200),
    "bug":           (255, 200,  0),
    "news":          (0,  212, 255),
}

THREAT_COLORS = {
    "CRITICAL": (220,  50,  50),
    "HIGH":     (255, 140,   0),
    "MEDIUM":   (255, 200,   0),
    "LOW":      (  0, 220, 120),
}

_CVSS_RE = re.compile(r"CVSS\s*(?:score\s*)?([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_CVE_RE  = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)


def _threat_level(title: str, desc: str) -> tuple[str, str]:
    corpus = (title + " " + desc).lower()
    m = _CVSS_RE.search(corpus)
    if m:
        s = float(m.group(1))
        if s >= 9: return "🔴", "CRITICAL"
        if s >= 7: return "🟠", "HIGH"
        if s >= 4: return "🟡", "MEDIUM"
        return "🟢", "LOW"
    for kw in ("critical", "rce", "remote code", "0day", "zero-day", "unauthenticated"):
        if kw in corpus: return "🔴", "CRITICAL"
    for kw in ("high", "privilege escalation", "auth bypass", "ransomware"):
        if kw in corpus: return "🟠", "HIGH"
    return "🟡", "MEDIUM"


def _get_pil():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise ImportError("Pillow required: pip install Pillow") from exc


def _load_font(ImageFont, size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _load_font_regular(ImageFont, size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _draw_gradient(draw, x0, y0, x1, y1, color_a, color_b):
    h = y1 - y0
    for y in range(h):
        r = int(color_a[0] + (color_b[0] - color_a[0]) * y / h)
        g = int(color_a[1] + (color_b[1] - color_a[1]) * y / h)
        b = int(color_a[2] + (color_b[2] - color_a[2]) * y / h)
        draw.line([(x0, y0 + y), (x1, y0 + y)], fill=(r, g, b))


def _draw_grid(draw, x0, y0, x1, y1, step=50):
    for x in range(x0, x1, step):
        draw.line([(x, y0), (x, y1)], fill=(0, 40, 70), width=1)
    for y in range(y0, y1, step):
        draw.line([(x0, y), (x1, y)], fill=(0, 40, 70), width=1)


def _wrap(text: str, chars: int) -> list[str]:
    return textwrap.wrap(text, width=chars) or [text[:chars]]


def generate_deep_image(
    item: dict[str, Any],
    out_dir: Path,
    fix_steps: list[str] | None = None,
    prev_steps: list[str] | None = None,
    size: tuple[int, int] = (LINKEDIN_W, LINKEDIN_H),
) -> tuple[Path, Path]:
    """
    Renders two-panel deep image:
      Left  — headline, threat badge, category, CVE
      Right — FIX & PREVENT bullet lists
    """
    Image, ImageDraw, ImageFont = _get_pil()
    W, H = size
    SPLIT = int(W * 0.52)   # left panel width

    title    = item.get("title", "Security Alert")
    desc     = item.get("description", "")
    category = item.get("category", "news")
    source   = item.get("source", "")
    accent   = CATEGORY_ACCENT.get(category, PALETTE["cyan"])
    _, level = _threat_level(title, desc)
    threat_color = THREAT_COLORS.get(level, PALETTE["yellow"])

    cve_m = _CVE_RE.search(title + " " + item.get("url", ""))
    cve_id = cve_m.group(0).upper() if cve_m else None

    # Default fix/prevent if not provided
    if not fix_steps or not prev_steps:
        from generators.deep_caption import FIX_GUIDES, _pick_n
        guide = FIX_GUIDES.get(category, FIX_GUIDES["news"])
        fix_steps  = fix_steps  or _pick_n(guide["fix"],     3, seed=title)
        prev_steps = prev_steps or _pick_n(guide["prevent"], 3, seed=title + "p")

    # ── RAW: full background ────────────────────────────────────────────────
    raw = Image.new("RGB", (W, H), PALETTE["bg_dark"])
    rd  = ImageDraw.Draw(raw)
    _draw_gradient(rd, 0, 0, W, H, PALETTE["bg_dark"], PALETTE["bg_card"])
    _draw_grid(rd, 0, 0, W, H)
    # Vertical divider
    rd.line([(SPLIT, 0), (SPLIT, H)], fill=accent, width=3)
    # Left accent bar
    rd.rectangle([(0, 0), (6, H)], fill=accent)
    # Corner glow simulation
    for i in range(5):
        alpha = 15 - i * 2
        rd.ellipse([-60 + i*5, -60 + i*5, 120 - i*5, 120 - i*5], fill=PALETTE["bg_panel"])

    raw_path = out_dir / "image_raw.png"
    raw.save(str(raw_path), "PNG", optimize=True)

    # ── FINAL: raw + all text ──────────────────────────────────────────────
    final = raw.copy()
    draw  = ImageDraw.Draw(final)

    f_huge   = _load_font(ImageFont, 54 if W >= 1200 else 44)
    f_large  = _load_font(ImageFont, 36)
    f_med    = _load_font(ImageFont, 26)
    f_small  = _load_font(ImageFont, 20)
    f_reg    = _load_font_regular(ImageFont, 22)
    f_tiny   = _load_font(ImageFont, 18)

    margin = 36
    y = margin + 10

    # ── LEFT PANEL ────────────────────────────────────────────────────────
    # Threat level badge
    badge = f" {level} "
    bw = len(badge) * 20
    draw.rounded_rectangle([margin, y, margin + bw, y + 38], radius=5, fill=threat_color)
    draw.text((margin + 8, y + 6), badge.strip(), fill=PALETTE["bg_dark"], font=f_med)
    y += 52

    # Category badge
    cat_txt = f" {category.upper()} "
    draw.rounded_rectangle([margin, y, margin + len(cat_txt) * 15, y + 30], radius=4, fill=accent)
    draw.text((margin + 6, y + 4), cat_txt.strip(), fill=PALETTE["bg_dark"], font=f_small)
    y += 46

    # CVE ID (if present)
    if cve_id:
        draw.text((margin, y), cve_id, fill=PALETTE["cyan"], font=f_large)
        y += 44

    # Title (wrapped)
    max_chars = 26 if W >= 1200 else 20
    title_lines = _wrap(title, max_chars)[:4]
    for line in title_lines:
        draw.text((margin, y), line, fill=PALETTE["white"], font=f_huge if len(title) < 50 else f_large)
        y += (62 if len(title) < 50 else 44)

    y += 8
    draw.line([(margin, y), (SPLIT - 20, y)], fill=accent, width=2)
    y += 14

    # Source
    if source:
        draw.text((margin, y), f"Source: {source}", fill=PALETTE["muted"], font=f_tiny)
        y += 28

    # Brand tagline bottom-left
    draw.text((margin, H - 56), f"🔐 {BRAND['website_url']}", fill=PALETTE["cyan"], font=f_small)
    draw.text((margin, H - 30), BRAND["watermark_text"], fill=PALETTE["muted"], font=f_tiny)

    # ── RIGHT PANEL ───────────────────────────────────────────────────────
    rx = SPLIT + margin
    ry = margin + 10

    # HOW TO FIX header
    draw.text((rx, ry), "🔧 HOW TO FIX", fill=PALETTE["green"], font=f_large)
    ry += 42
    draw.line([(rx, ry), (W - margin, ry)], fill=PALETTE["green"], width=1)
    ry += 12

    right_w = W - rx - margin
    chars_r = max(20, right_w // 13)

    for i, step in enumerate(fix_steps[:3]):
        num_col = PALETTE["cyan"]
        draw.text((rx, ry), f"{'①②③'[i]}", fill=num_col, font=f_med)
        wrapped = _wrap(step, chars_r - 3)
        for j, wl in enumerate(wrapped[:2]):
            draw.text((rx + 28, ry + j * 24), wl, fill=PALETTE["text"], font=f_reg)
        ry += max(26 * len(wrapped[:2]), 28) + 8

    ry += 10

    # HOW TO PREVENT header
    draw.text((rx, ry), "🛡️ HOW TO PREVENT", fill=PALETTE["orange"], font=f_large)
    ry += 42
    draw.line([(rx, ry), (W - margin, ry)], fill=PALETTE["orange"], width=1)
    ry += 12

    bullets = "◆◇▸▹"
    for i, step in enumerate(prev_steps[:4]):
        b_col = PALETTE["cyan"]
        draw.text((rx, ry), bullets[i % len(bullets)], fill=b_col, font=f_small)
        wrapped = _wrap(step, chars_r - 3)
        for j, wl in enumerate(wrapped[:2]):
            draw.text((rx + 22, ry + j * 22), wl, fill=PALETTE["muted"], font=f_reg)
        ry += max(24 * len(wrapped[:2]), 26) + 6

    final_path = out_dir / "image.png"
    final.save(str(final_path), "PNG", optimize=True)
    log.info("Saved deep images → %s", out_dir)
    return raw_path, final_path


def generate(
    item: dict[str, Any],
    out_dir: Path,
    config: dict[str, Any] | None = None,
    fix_steps: list[str] | None = None,
    prev_steps: list[str] | None = None,
    size: tuple[int, int] | None = None,
) -> tuple[Path, Path]:
    """Public entry point. Falls back to standard placeholder on error."""
    cfg = config or {}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    img_size = size or (
        (SQUARE_W, SQUARE_H) if cfg.get("image_size") == "square"
        else (LINKEDIN_W, LINKEDIN_H)
    )

    depth = cfg.get("image_depth", "deep")
    if depth == "standard":
        from generators.image_generator import generate as std_gen
        return std_gen(item, out_dir, cfg)

    try:
        return generate_deep_image(item, out_dir, fix_steps, prev_steps, img_size)
    except Exception as exc:
        log.warning("Deep image failed (%s); falling back to placeholder.", exc)
        from generators.image_generator import generate_placeholder
        return generate_placeholder(item, out_dir, img_size)
