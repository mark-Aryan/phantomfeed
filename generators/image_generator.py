"""
generators/image_generator.py
==============================
Creates branded LinkedIn images in two backends:

  (A) PLACEHOLDER  – Pillow only, always available CPU-only
  (B) REMOTE API   – HuggingFace / StabilityAI text-to-image, with fallback

Output files:
  image_raw.png   – source / generated image (no text overlay)
  image.png       – final with title overlay + watermark

LinkedIn optimal sizes: 1200×627 (default) or 1080×1080

HUMAN REVIEW: Adjust PALETTE, FONT_SIZE, and LAYOUT constants to match brand.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import textwrap
from pathlib import Path
from typing import Any

from brand.brand_config import BRAND

log = logging.getLogger(__name__)

# ── Layout constants ──────────────────────────────────────────────────────────
LINKEDIN_W, LINKEDIN_H = 1200, 627
SQUARE_W, SQUARE_H = 1080, 1080

# Dark cyber-themed palette matching codeXploit brand (#05050f / #00d4ff)
PALETTE = {
    "bg_dark":   (5, 5, 15),
    "bg_card":   (13, 13, 30),
    "cyan":      (0, 212, 255),
    "blue":      (0, 75, 204),
    "text":      (232, 234, 240),
    "muted":     (136, 146, 164),
    "white":     (255, 255, 255),
    "accent":    (26, 110, 247),
    "red_alert": (220, 50, 50),
}

CATEGORY_ACCENT: dict[str, tuple[int, int, int]] = {
    "vulnerability": (220, 50, 50),
    "incident":      (255, 140, 0),
    "fraud":         (200, 0, 200),
    "bug":           (255, 200, 0),
    "news":          (0, 212, 255),
}


# ─────────────────────────────────────────────────────────────────────────────

def _get_pil():
    """Import Pillow lazily so the module loads even if PIL is missing."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise ImportError(
            "Pillow is required: pip install Pillow"
        ) from exc


def _load_font(ImageFont, size: int):
    """Try to load a TTF font; fall back to Pillow default."""
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _draw_gradient(draw, width: int, height: int) -> None:
    """Draw a vertical gradient background."""
    from PIL import Image
    for y in range(height):
        ratio = y / height
        r = int(PALETTE["bg_dark"][0] * (1 - ratio) + PALETTE["bg_card"][0] * ratio)
        g = int(PALETTE["bg_dark"][1] * (1 - ratio) + PALETTE["bg_card"][1] * ratio)
        b = int(PALETTE["bg_dark"][2] * (1 - ratio) + PALETTE["bg_card"][2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def _draw_grid(draw, width: int, height: int) -> None:
    """Draw subtle grid lines matching codeXploit style."""
    grid_color = (0, 212, 255, 20)
    step = 60
    for x in range(0, width, step):
        draw.line([(x, 0), (x, height)], fill=(0, 50, 80), width=1)
    for y in range(0, height, step):
        draw.line([(0, y), (width, y)], fill=(0, 50, 80), width=1)


def _wrap_text(text: str, max_chars: int = 42) -> list[str]:
    return textwrap.wrap(text, width=max_chars) or [text[:max_chars]]


def generate_placeholder(
    item: dict[str, Any],
    out_dir: Path,
    size: tuple[int, int] = (LINKEDIN_W, LINKEDIN_H),
) -> tuple[Path, Path]:
    """
    Generate a branded placeholder image using Pillow only.

    Returns (raw_path, final_path).
    """
    Image, ImageDraw, ImageFont = _get_pil()
    W, H = size
    category = item.get("category", "news")
    title = item.get("title", "Security Update")
    source = item.get("source", "")

    accent = CATEGORY_ACCENT.get(category, PALETTE["cyan"])

    # ── RAW image (background only) ──────────────────────────────────────────
    raw = Image.new("RGB", (W, H), PALETTE["bg_dark"])
    raw_draw = ImageDraw.Draw(raw)
    _draw_gradient(raw_draw, W, H)
    _draw_grid(raw_draw, W, H)

    # Accent bar at left edge
    raw_draw.rectangle([(0, 0), (8, H)], fill=accent)

    # Corner glows (simple rectangles with transparency simulation)
    raw_draw.ellipse([(-80, -80), (160, 160)], fill=(0, 75, 204, 15) if False else PALETTE["bg_card"])
    raw_draw.ellipse([(W - 160, H - 160), (W + 80, H + 80)], fill=PALETTE["bg_card"])

    raw_path = out_dir / "image_raw.png"
    raw.save(str(raw_path), "PNG", optimize=True)

    # ── FINAL image (raw + text overlay) ─────────────────────────────────────
    final = raw.copy()
    draw = ImageDraw.Draw(final)

    font_title = _load_font(ImageFont, 52 if W >= 1200 else 42)
    font_label = _load_font(ImageFont, 28)
    font_small = _load_font(ImageFont, 22)
    font_wm    = _load_font(ImageFont, 24)

    margin = 60
    y = 60

    # Category badge
    badge_text = f"  {category.upper()}  "
    draw.rounded_rectangle(
        [margin, y, margin + len(badge_text) * 16, y + 44],
        radius=6, fill=accent,
    )
    draw.text((margin + 10, y + 8), badge_text.strip(), fill=PALETTE["bg_dark"], font=font_label)
    y += 70

    # Title (wrapped, max 3 lines)
    lines = _wrap_text(title, max_chars=44 if W >= 1200 else 34)[:3]
    for line in lines:
        draw.text((margin, y), line, fill=PALETTE["white"], font=font_title)
        y += 64

    y += 20

    # Horizontal divider
    draw.line([(margin, y), (W - margin, y)], fill=accent, width=2)
    y += 28

    # Source line
    if source:
        draw.text((margin, y), f"Source: {source}", fill=PALETTE["muted"], font=font_small)
        y += 36

    # Brand tagline
    tagline = f"🔐 {BRAND['job_title']} | {BRAND['website_url']}"
    draw.text((margin, H - 80), tagline, fill=PALETTE["cyan"], font=font_small)

    # Watermark bottom-right
    wm = BRAND["watermark_text"]
    draw.text((W - margin - len(wm) * 13, H - 45), wm, fill=PALETTE["muted"], font=font_wm)

    final_path = out_dir / "image.png"
    final.save(str(final_path), "PNG", optimize=True)
    log.info("Saved placeholder images → %s", out_dir)
    return raw_path, final_path


def generate_remote(
    item: dict[str, Any],
    out_dir: Path,
    config: dict[str, Any],
    size: tuple[int, int] = (LINKEDIN_W, LINKEDIN_H),
) -> tuple[Path, Path]:
    """
    Generate image via HuggingFace / StabilityAI API.

    Falls back to placeholder on any error.
    """
    try:
        return _call_hf_api(item, out_dir, config, size)
    except Exception as exc:
        log.warning("Remote image generation failed (%s); using placeholder.", exc)
        return generate_placeholder(item, out_dir, size)


def _call_hf_api(
    item: dict[str, Any],
    out_dir: Path,
    config: dict[str, Any],
    size: tuple[int, int],
) -> tuple[Path, Path]:
    """Call HuggingFace text-to-image inference endpoint."""
    import urllib.request
    import json

    Image, ImageDraw, ImageFont = _get_pil()

    W, H = size
    category = item.get("category", "news")
    title = item.get("title", "security update")[:80]
    token = config.get("hf_api_token", "")
    model = config.get(
        "hf_image_model",
        "stabilityai/stable-diffusion-2-1-base",
    )

    prompt = (
        f"Cybersecurity concept art, dark blue and cyan color scheme, "
        f"digital network visualization, representing '{title}', "
        f"professional LinkedIn post image, no text, high quality, "
        f"8k, codeXploit brand aesthetic"
    )

    url = f"https://api-inference.huggingface.co/models/{model}"
    payload = json.dumps({"inputs": prompt}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        img_bytes = resp.read()

    raw_img = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((W, H))
    raw_path = out_dir / "image_raw.png"
    raw_img.save(str(raw_path), "PNG")

    # Overlay title
    final_path = _overlay_title(raw_img, item, out_dir, W, H, ImageDraw, ImageFont)
    return raw_path, final_path


def _overlay_title(
    img,
    item: dict[str, Any],
    out_dir: Path,
    W: int,
    H: int,
    ImageDraw,
    ImageFont,
) -> Path:
    """Add title text and watermark overlay onto an existing image."""
    from PIL import Image as PILImage

    overlay = img.copy()
    draw = ImageDraw.Draw(overlay)
    font_title = _load_font(ImageFont, 48)
    font_wm = _load_font(ImageFont, 22)

    title = item.get("title", "")
    lines = _wrap_text(title, 42)[:3]

    # Semi-transparent bottom bar
    bar_h = len(lines) * 68 + 80
    bar = PILImage.new("RGBA", (W, bar_h), (5, 5, 15, 200))
    overlay.paste(PILImage.fromarray(
        __import__("numpy").array(bar) if False else bar.convert("RGB")
    ), (0, H - bar_h), bar)

    y = H - bar_h + 20
    for line in lines:
        draw.text((40, y), line, fill=PALETTE["white"], font=font_title)
        y += 64

    wm = BRAND["watermark_text"]
    draw.text((W - 320, H - 36), wm, fill=PALETTE["muted"], font=font_wm)

    final_path = out_dir / "image.png"
    overlay.save(str(final_path), "PNG")
    return final_path


def generate(
    item: dict[str, Any],
    out_dir: Path,
    config: dict[str, Any] | None = None,
    size: tuple[int, int] | None = None,
) -> tuple[Path, Path]:
    """
    Public entry point.

    Respects config['image_backend']:
      "placeholder" (default, no API key needed)
      "remote"      (HuggingFace / StabilityAI)

    Returns (raw_path, final_path).
    """
    cfg = config or {}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    img_size = size or (
        (SQUARE_W, SQUARE_H)
        if cfg.get("image_size") == "square"
        else (LINKEDIN_W, LINKEDIN_H)
    )

    if cfg.get("image_backend") == "remote" and cfg.get("hf_api_token"):
        return generate_remote(item, out_dir, cfg, img_size)
    return generate_placeholder(item, out_dir, img_size)
