# =============================================================================
# pipeline/classifier.py — PhantomFeed v2
# =============================================================================
# Copyright (c) 2026 Aryan Kumar Upadhyay (@aryankrupadhyay)
# Brand: codeXploit · https://codexploit.in
# License: MIT — Retain this header and brand attribution in all copies.
#
# CHANGES IN THIS VERSION
# ────────────────────────
# FIX-1  "bug" category: removed r"\berror\b" (too broad — matches "an error
#        occurred in the system" type news items, producing false positives).
#        Replaced with tighter patterns that require security context.
# FIX-2  All patterns compiled once at import time for O(1) amortised match.
# ADD-1  Added "supply_chain" signals under "incident" category (SolarWinds-type
#        attacks, dependency confusion, typosquatting).
# ADD-2  Added "insider_threat" signals under "incident".
# =============================================================================

from __future__ import annotations

import re
from typing import Sequence

# ── Category rules ─────────────────────────────────────────────────────────────
# Format: (category_name, [keyword_patterns], min_matches_required)
# Evaluated in order — first match wins.

RULES: list[tuple[str, list[str], int]] = [
    (
        "vulnerability",
        [
            r"\bCVE-\d{4}-\d+\b",
            r"\bvulnerabilit",
            r"\bsecurity flaw\b",
            r"\bzero.?day\b",
            r"\b0day\b",
            r"\bremote code exec",
            r"\bRCE\b",
            r"\bsql injection\b",
            r"\bXSS\b",
            r"\bCVSS\b",
            r"\bpatch\b",
            r"\bexploit\b",
            r"\bprivilege escalation\b",
            r"\bauth bypass\b",
            r"\bbuffer overflow\b",
            r"\bheap overflow\b",
            r"\buse.after.free\b",
            r"\bpath traversal\b",
            r"\bSSRF\b",
            r"\bXXE\b",
            r"\binjection\b",
            r"\bdeserialization\b",
            r"\bopen redirect\b",
            r"\binsecure direct object\b",
            r"\bbroken access control\b",
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
            r"\bcredential harvest",
            r"\bfake (login|page|portal)\b",
        ],
        1,
    ),
    (
        "bug",
        [
            # FIX-1: Removed r"\berror\b" and r"\bcrash\b" — too broad.
            # Now require security-adjacent context words.
            r"\bsecurity bug\b",
            r"\bsoftware flaw\b",
            r"\bmemory leak\b",
            r"\bnull pointer\b",
            r"\bnull dereference\b",
            r"\brace condition\b",
            r"\buse after free\b",
            r"\bdouble free\b",
            r"\binteger overflow\b",
            r"\btype confusion\b",
            r"\bformat string bug\b",
        ],
        1,
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
            r"\bexfiltrat",              # exfiltrate / exfiltration
            r"\btrojan\b",
            r"\bbackdoor\b",
            r"\bwiper\b",
            r"\bspyware\b",
            r"\bkeylogger\b",
            # ADD-1: supply chain
            r"\bsupply chain attack\b",
            r"\bdependency confusion\b",
            r"\btyposquat",
            # ADD-2: insider threat
            r"\binsider threat\b",
            r"\brogue employee\b",
        ],
        1,
    ),
]

# FIX-2: Compile all patterns once at import time
_COMPILED_RULES: list[tuple[str, list[re.Pattern], int]] = [
    (cat, [re.compile(p, re.IGNORECASE) for p in patterns], min_matches)
    for cat, patterns, min_matches in RULES
]


def classify(title: str, description: str = "") -> str:
    """
    Return category string for a news item.

    Checks (title + description) against RULES in order;
    returns first matching category, or 'news' as fallback.
    """
    corpus = title + " " + description
    for category, patterns, min_matches in _COMPILED_RULES:
        hits = sum(1 for p in patterns if p.search(corpus))
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
