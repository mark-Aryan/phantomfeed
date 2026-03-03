# =============================================================================
# pipeline/safety_filter.py — PhantomFeed v2
# =============================================================================
# Copyright (c) 2026 Aryan Kumar Upadhyay (@aryankrupadhyay)
# Brand: codeXploit · https://codexploit.in
# License: MIT — Retain this header and brand attribution in all copies.
#
# PURPOSE
# ───────
# Detects and flags items that may contain PoC code, exploit steps,
# or other actionable attack details.
#
# Items flagged as "manual_review" are NOT auto-processed.
# A review.txt is written explaining the match. A human must run
# `python cli_v2.py reprocess <id>` to publish after review.
#
# See SAFETY.md for the complete policy.
#
# CHANGES IN THIS VERSION
# ────────────────────────
# ADD-1  Added patterns for CVE PoC GitHub repos, web shell uploads,
#        and common SQL injection demonstration strings.
# ADD-2  redact() now also strips SQL injection demonstration strings.
# OPT-1  Patterns are compiled once at import time (already correct —
#        preserved and explicitly documented here).
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Patterns that trigger manual review ───────────────────────────────────────
# Keep this list auditable — one pattern per line with a comment.
# Update SAFETY.md whenever you add a pattern here.

REDACTION_PATTERNS: list[str] = [
    # Code blocks
    r"```",                                          # fenced code block
    r"<code>",                                       # HTML code tag

    # Shell / terminal indicators
    r"\$\s+[a-z]+\s",                               # shell prompt "$ command"
    r"(?i)\bgetshell\b",                            # exploitation success term
    r"(?i)\bpayload\b",                             # attack payload
    r"(?i)\bexploit\.py\b",                         # named exploit script

    # Proof-of-concept markers
    r"(?i)\bpoc\b",                                 # PoC abbreviation
    r"(?i)\bproof.of.concept\b",                    # spelled out
    r"(?i)\bstep.by.step.exploit",                  # walkthrough language
    r"(?i)\bhow to exploit\b",                      # enablement phrase
    r"(?i)\battack.walkthrough",                    # walkthrough language

    # Metasploit / exploit framework
    r"(?i)\bmsfvenom\b",                            # MSF payload generator
    r"(?i)\bmetasploit.*use\b",                     # MSF module loading
    r"(?i)\bshellcode\b",                           # raw machine code

    # Reverse shells
    r"(?i)\bnc\s+-e\b",                             # netcat reverse shell
    r"(?i)\bbash\s+-i\s+>&",                        # bash reverse shell
    r"(?i)\bpython\s+-c\s+['\"]import socket",      # Python reverse shell
    r"(?i)\bcurl.*\|\s*bash",                       # pipe-to-bash
    r"(?i)\bwget.*-O\s*-.*\|\s*sh",                 # wget pipe-to-shell

    # Step-by-step patterns
    r"(?i)step\s+\d+\s*[:\-]\s*(run|execute|upload|download|inject)",
    r"(?i)\bfull\s+exploit\s+(code|walkthrough|tutorial)",

    # Web shell / file upload exploitation
    r"(?i)\bweb\s*shell\s+(upload|deploy|inject)",  # ADD-1
    r"(?i)\bupload.*\.php.*shell",                   # ADD-1
    r"(?i)\bc99\.php\b",                             # ADD-1 (known web shell)
    r"(?i)\br57\.php\b",                             # ADD-1 (known web shell)

    # SQL injection demonstrations
    r"(?i)'\s*OR\s*'1'\s*=\s*'1",                   # ADD-1 classic SQLi demo
    r"(?i)UNION\s+SELECT\s+NULL",                    # ADD-1 SQLi union demo

    # CVE PoC repository patterns
    r"(?i)github\.com/.*[Pp][Oo][Cc].*CVE",         # ADD-1 GitHub PoC repo links
    r"(?i)exploitdb\.com",                           # Exploit-DB direct links
]

# OPT-1: Compile once at import time — not inside check() on every call
_COMPILED: list[re.Pattern] = [re.compile(p) for p in REDACTION_PATTERNS]


# ── Result type ────────────────────────────────────────────────────────────────

@dataclass
class SafetyResult:
    is_safe: bool = True
    reasons: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return "safe" if self.is_safe else "manual_review"


# ── Public API ─────────────────────────────────────────────────────────────────

def check(item: dict) -> SafetyResult:
    """
    Check a feed item dict for PoC / exploit content.
    Inspects 'title', 'description', and 'content' fields.
    """
    corpus = " ".join([
        item.get("title", ""),
        item.get("description", ""),
        item.get("content", ""),
    ])
    result = SafetyResult()
    for regex in _COMPILED:
        m = regex.search(corpus)
        if m:
            result.is_safe = False
            snippet = corpus[max(0, m.start() - 20): m.end() + 20].strip()
            result.reasons.append(
                f"Pattern '{regex.pattern}' matched near: «{snippet}»"
            )
    return result


def redact(text: str) -> str:
    """
    Remove code-block-like spans from text.
    Used only for safe preview in review.txt — never in published content.
    """
    # Fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "[CODE REDACTED]", text)
    text = re.sub(r"`[^`]+`", "[CODE REDACTED]", text)
    # HTML code tags
    text = re.sub(r"<code>[\s\S]*?</code>", "[CODE REDACTED]", text, flags=re.IGNORECASE)
    # ADD-2: SQL injection demo strings
    text = re.sub(r"'[\s]*OR[\s]*'1'[\s]*=[\s]*'1[^']*'", "[SQLI REDACTED]", text, flags=re.IGNORECASE)
    return text


def review_text(item: dict, reasons: list[str]) -> str:
    """Generate the content for review.txt when an item is flagged."""
    lines = [
        "=== MANUAL REVIEW REQUIRED ===",
        "",
        f"Title    : {item.get('title', 'N/A')}",
        f"Source   : {item.get('source', 'N/A')}",
        f"URL      : {item.get('url', 'N/A')}",
        f"Published: {item.get('published_at', 'N/A')}",
        f"Category : {item.get('category', 'N/A')}",
        "",
        "Reasons flagged:",
    ]
    for i, r in enumerate(reasons, 1):
        lines.append(f"  {i}. {r}")
    lines += [
        "",
        "─" * 60,
        "Action required:",
        "  A human reviewer must evaluate this item before any",
        "  caption or image is generated and published.",
        "",
        "  If safe to publish:",
        "    python cli_v2.py reprocess \"" + item.get("canonical_id", "<id>") + "\"",
        "",
        "  If it contains exploit details: archive the folder, do not publish.",
        "",
        "Policy reference: SAFETY.md",
        f"Brand: codeXploit · https://codexploit.in",
        f"Copyright (c) 2026 Aryan Kumar Upadhyay",
    ]
    return "\n".join(lines)
