"""
pipeline/safety_filter.py
==========================
Detects and flags items that may contain PoC code, exploit steps,
or other actionable attack details.

Items flagged as "manual_review" are NOT auto-processed;
instead a review.txt is written explaining why.

See SAFETY.md for the full policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Patterns that trigger manual review ────────────────────────────────────────
# Add patterns here to expand coverage; keep them auditable.
REDACTION_PATTERNS: list[str] = [
    # Code blocks / shells
    r"```",
    r"<code>",
    r"\$\s+[a-z]+\s",          # shell prompt
    r"(?i)\bgetshell\b",
    r"(?i)\bpayload\b",
    r"(?i)\bexploit\.py\b",
    r"(?i)\bpoc\b",
    r"(?i)\bproof.of.concept\b",
    r"(?i)\bstep.by.step.exploit",
    r"(?i)\bhow to exploit\b",
    r"(?i)\battack.walkthrough",
    # Common exploit keywords in context
    r"(?i)\bmsfvenom\b",
    r"(?i)\bmetasploit.*use\b",
    r"(?i)\bshellcode\b",
    r"(?i)\bnc\s+-e\b",          # netcat reverse shell
    r"(?i)\bbash\s+-i\s+>&",     # bash reverse shell
    r"(?i)\bpython\s+-c\s+['\"]import socket",
    r"(?i)\bcurl.*\|\s*bash",
    r"(?i)\bwget.*-O\s*-.*\|\s*sh",
    # Step-by-step patterns
    r"(?i)step\s+\d+\s*[:\-]\s*(run|execute|upload|download|inject)",
    r"(?i)\bfull\s+exploit\s+(code|walkthrough|tutorial)",
]

_COMPILED = [re.compile(p) for p in REDACTION_PATTERNS]


@dataclass
class SafetyResult:
    is_safe: bool = True
    reasons: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return "safe" if self.is_safe else "manual_review"


def check(item: dict) -> SafetyResult:
    """Check a feed item dict for PoC / exploit content.

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
            result.reasons.append(
                f"Pattern '{regex.pattern}' matched near: "
                f"«{corpus[max(0,m.start()-20):m.end()+20].strip()}»"
            )
    return result


def redact(text: str) -> str:
    """Remove code-block-like spans from text (for safe preview only)."""
    # Remove fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "[CODE REDACTED]", text)
    text = re.sub(r"`[^`]+`", "[CODE REDACTED]", text)
    # Remove HTML code tags
    text = re.sub(r"<code>[\s\S]*?</code>", "[CODE REDACTED]", text, flags=re.IGNORECASE)
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
        "",
        "Reasons flagged:",
    ]
    for i, r in enumerate(reasons, 1):
        lines.append(f"  {i}. {r}")
    lines += [
        "",
        "Action: A human reviewer must evaluate this item before any",
        "        caption or image is generated and published.",
        "",
        "Policy reference: SAFETY.md",
    ]
    return "\n".join(lines)
