"""
pipeline/classifier.py
======================
Keyword-based category classifier.  Extensible: add new categories
by appending entries to RULES below — no code changes needed.

Categories: vulnerability | fraud | bug | incident | news
"""

from __future__ import annotations

import re
from typing import Sequence

# ── Category rules ─────────────────────────────────────────────────────────────
# Each tuple: (category_name, [keyword_patterns], min_matches)
RULES: list[tuple[str, list[str], int]] = [
    (
        "vulnerability",
        [
            r"\bCVE-\d{4}-\d+\b",
            r"\bvulnerabilit",
            r"\bsecurity flaw",
            r"\bzero.?day",
            r"\b0day\b",
            r"\bremote code exec",
            r"\bRCE\b",
            r"\bsql injection\b",
            r"\bXSS\b",
            r"\bCVSS\b",
            r"\bpatch\b",
            r"\bexploit\b",
            r"\bprivilege escalation\b",
            r"\bauth bypass",
            r"\bbuffer overflow",
            r"\bheap overflow",
            r"\buse.after.free",
            r"\bpath traversal",
            r"\bSSRF\b",
            r"\bXXE\b",
            r"\binjection\b",
            r"\bdeserialization\b",
        ],
        1,
    ),
    (
        "fraud",
        [
            r"\bphishing\b",
            r"\bscam\b",
            r"\bfraud\b",
            r"\bidentity theft\b",
            r"\bsocial engineering\b",
            r"\bbusiness email compromise\b",
            r"\bBEC\b",
            r"\bcredit card\b",
            r"\bspoofing\b",
            r"\bvishing\b",
            r"\bsmishing\b",
        ],
        1,
    ),
    (
        "bug",
        [
            r"\bbug\b",
            r"\bdefect\b",
            r"\bsoftware flaw\b",
            r"\berror\b",
            r"\bcrash\b",
            r"\bmemory leak\b",
            r"\bnull pointer\b",
            r"\brace condition\b",
        ],
        2,
    ),
    (
        "incident",
        [
            r"\bbreach\b",
            r"\bdata leak\b",
            r"\bhacked\b",
            r"\bransomware\b",
            r"\bcyberattack\b",
            r"\bmalware\b",
            r"\bDDoS\b",
            r"\bdata stolen\b",
            r"\bcompromised\b",
            r"\battack\b",
            r"\binfiltrated\b",
            r"\bthreat actor\b",
            r"\bAPT\b",
        ],
        1,
    ),
]


def classify(title: str, description: str = "") -> str:
    """Return category string for a news item.

    Checks title + description text against RULES in order;
    returns first matching category, or 'news' as fallback.
    """
    corpus = (title + " " + description).lower()
    for category, patterns, min_matches in RULES:
        hits = sum(
            1 for p in patterns if re.search(p, corpus, re.IGNORECASE)
        )
        if hits >= min_matches:
            return category
    return "news"


def classify_batch(items: Sequence[dict]) -> list[dict]:
    """Add 'category' key to each item dict in-place and return the list."""
    for item in items:
        item["category"] = classify(
            item.get("title", ""), item.get("description", "")
        )
    return list(items)
