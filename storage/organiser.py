"""
storage/organiser.py
====================
Saves generated assets into:
  out/<category>/<YYYY-MM-DD>/<slug>-<short_id>/
    image.png
    image_raw.png
    post.txt
    meta.json
    [review.txt]   — only when safety-flagged

Slug collisions are avoided by appending a 6-char hash of the canonical ID.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _slug_safe(text: str, max_len: int = 40) -> str:
    t = text.lower()
    t = re.sub(r"[^a-z0-9\s-]", "", t)
    t = re.sub(r"[\s-]+", "-", t).strip("-")
    return t[:max_len]


def item_dir(
    base_out: str | Path,
    item: dict[str, Any],
    canonical_id: str,
) -> Path:
    """
    Compute the output directory path for a given item.
    Creates the directory if it doesn't exist.
    """
    category = item.get("category", "news")
    pub = item.get("published_at", "")
    try:
        date_str = datetime.fromisoformat(pub.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    title = item.get("title", "untitled")
    slug = _slug_safe(title)
    short_id = hashlib.sha256(canonical_id.encode()).hexdigest()[:6]
    folder_name = f"{slug}-{short_id}"

    out = Path(base_out) / category / date_str / folder_name
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_post(out_dir: Path, caption: str, item: dict[str, Any]) -> Path:
    """Write the SEO caption + meta header to post.txt."""
    path = out_dir / "post.txt"
    header = (
        f"# codeXploit Security Post\n"
        f"# Title    : {item.get('title', '')}\n"
        f"# Category : {item.get('category', '')}\n"
        f"# Source   : {item.get('source', '')}\n"
        f"# URL      : {item.get('url', '')}\n"
        f"# Generated: {datetime.now(timezone.utc).isoformat()}\n"
        f"{'─' * 60}\n\n"
    )
    path.write_text(header + caption, encoding="utf-8")
    return path


def save_meta(out_dir: Path, item: dict[str, Any], canonical_id: str) -> Path:
    """Write meta.json with raw metadata."""
    meta = {
        "canonical_id": canonical_id,
        "title": item.get("title", ""),
        "description": item.get("description", ""),
        "url": item.get("url", ""),
        "source": item.get("source", ""),
        "published_at": item.get("published_at", ""),
        "category": item.get("category", "news"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = out_dir / "meta.json"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def save_review(out_dir: Path, review_content: str) -> Path:
    """Write review.txt for flagged items (no caption/image generated)."""
    path = out_dir / "review.txt"
    path.write_text(review_content, encoding="utf-8")
    return path


def copy_images(
    out_dir: Path,
    raw_path: Path | None,
    final_path: Path | None,
) -> None:
    """Move/copy generated images into out_dir if they're not already there."""
    for src, name in [(raw_path, "image_raw.png"), (final_path, "image.png")]:
        if src and src.exists():
            dest = out_dir / name
            if src.resolve() != dest.resolve():
                shutil.copy2(str(src), str(dest))
