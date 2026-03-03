"""
generators/text_generator.py
=============================
Generates SEO-optimised LinkedIn captions in two modes:

  (A) TEMPLATE  – fully offline, uses brand tokens from brand_config.py
  (B) AI        – calls Claude API or HuggingFace Inference API for richer text

SEO caption structure (exactly as specified):
  1. Hook line  (≤1 sentence) — primary keyword + year 2026
  2. 1-2 sentence summary
  3. 1 sentence remediation / action
  4. 3-6 hashtags  (brand + skill tags from index.html)
  5. Optional source reference / CTA

HUMAN REVIEW: Tweak TEMPLATES dict to change tone/structure.
"""

from __future__ import annotations

import hashlib
import random
import re
import textwrap
from typing import Any

from brand.brand_config import BRAND

# ── Caption templates ──────────────────────────────────────────────────────────
# Each template is a format string; available keys are documented inline.
TEMPLATES: dict[str, str] = {
    "vulnerability": (
        "{hook}\n\n"
        "{summary}\n\n"
        "{remediation}\n\n"
        "{hashtags}\n\n"
        "🔗 {url}"
    ),
    "incident": (
        "{hook}\n\n"
        "{summary}\n\n"
        "⚠️ {remediation}\n\n"
        "{hashtags}\n\n"
        "🔗 {url}"
    ),
    "fraud": (
        "{hook}\n\n"
        "{summary}\n\n"
        "🛡️ {remediation}\n\n"
        "{hashtags}\n\n"
        "🔗 {url}"
    ),
    "bug": (
        "{hook}\n\n"
        "{summary}\n\n"
        "{remediation}\n\n"
        "{hashtags}\n\n"
        "🔗 {url}"
    ),
    "news": (
        "{hook}\n\n"
        "{summary}\n\n"
        "{remediation}\n\n"
        "{hashtags}\n\n"
        "🔗 {url}"
    ),
}

# Hook prefixes per category
HOOK_PREFIXES: dict[str, list[str]] = {
    "vulnerability": [
        "🚨 Critical cybersecurity alert (2026):",
        "⚡ New vulnerability disclosed (2026):",
        "🔴 codeXploit Security Alert (2026):",
        "🛑 Vulnerability Advisory (2026):",
    ],
    "incident": [
        "🔥 Cyber incident confirmed (2026):",
        "⚠️ Security breach detected (2026):",
        "📢 Incident Alert — codeXploit (2026):",
    ],
    "fraud": [
        "🎣 Fraud campaign detected (2026):",
        "⚠️ Social-engineering threat (2026):",
        "🚫 Fraud Alert — codeXploit (2026):",
    ],
    "bug": [
        "🐛 Security-relevant bug reported (2026):",
        "🔧 Software flaw disclosed (2026):",
        "⚙️ Bug Advisory (2026):",
    ],
    "news": [
        "📰 Cybersecurity news (2026):",
        "🔐 InfoSec update — codeXploit (2026):",
        "💡 Security insight (2026):",
    ],
}

REMEDIATIONS: dict[str, list[str]] = {
    "vulnerability": [
        "✅ Apply the vendor patch immediately and test in staging first.",
        "✅ Update affected packages and audit dependent services.",
        "✅ Enable WAF rules and monitor for exploitation attempts.",
        "✅ Restrict network access to the vulnerable component now.",
    ],
    "incident": [
        "✅ Isolate affected systems, rotate credentials, and engage IR team.",
        "✅ Review access logs, revoke suspicious sessions, and patch gaps.",
        "✅ Activate your incident response playbook without delay.",
    ],
    "fraud": [
        "✅ Verify sender identity, enable MFA, and report suspicious messages.",
        "✅ Educate your team about this campaign and block known IOCs.",
        "✅ Enable email filtering and conduct awareness training.",
    ],
    "bug": [
        "✅ Apply the fix and re-test affected workflows.",
        "✅ Pin the patched version and run regression tests.",
        "✅ Update dependencies and audit for similar patterns.",
    ],
    "news": [
        "✅ Stay updated — follow codeXploit for daily security insights.",
        "✅ Audit your environment against the latest threat intelligence.",
        "✅ Share with your security team and review your posture.",
    ],
}

_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)


def _pick(lst: list[str], seed: str = "") -> str:
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(lst)
    return lst[idx]


def _build_hashtags(category: str, title: str, extra: list[str] | None = None) -> str:
    """Select 4-6 brand-aligned hashtags for the caption."""
    base = [BRAND["brand_hashtag"]]  # always first

    # Category-specific tags
    cat_tags: dict[str, list[str]] = {
        "vulnerability": ["#CVE", "#vulnerability", "#infosec", "#patchnow", "#OWASP"],
        "incident":      ["#cyberattack", "#incidentresponse", "#breach", "#infosec"],
        "fraud":         ["#phishing", "#fraud", "#socialeengineering", "#infosec"],
        "bug":           ["#bugbounty", "#securitybug", "#infosec", "#Python"],
        "news":          ["#cybersecurity", "#infosec", "#ethicalhacking"],
    }
    base.extend(cat_tags.get(category, cat_tags["news"]))

    # Pull from brand top_hashtags
    for ht in BRAND["top_hashtags"]:
        if ht not in base:
            base.append(ht)
        if len(base) >= 6:
            break

    # CVE-specific tag
    if _CVE_RE.search(title):
        base.insert(1, "#CVE")

    if extra:
        for e in extra:
            if len(base) < 7:
                base.append(e)

    # Dedupe, keep order
    seen: set[str] = set()
    deduped: list[str] = []
    for ht in base:
        lw = ht.lower()
        if lw not in seen:
            seen.add(lw)
            deduped.append(ht)

    return " ".join(deduped[:6])


def generate_template(item: dict[str, Any]) -> str:
    """
    Generate an SEO caption using offline templates.

    Args:
        item: Normalized feed item with at least 'title', 'description',
              'category', 'url', 'source'.

    Returns:
        Formatted LinkedIn caption string.
    """
    title = item.get("title", "Security Update")
    description = item.get("description", "")
    category = item.get("category", "news")
    url = item.get("url", BRAND["website_url"])
    source = item.get("source", "")

    # 1. Hook
    hook_prefix = _pick(HOOK_PREFIXES.get(category, HOOK_PREFIXES["news"]), seed=title)
    hook = f"{hook_prefix} {title}"

    # 2. Summary (truncate description to 2 sentences / 200 chars)
    sentences = re.split(r"(?<=[.!?])\s+", description.strip())
    summary = " ".join(sentences[:2])
    if len(summary) > 250:
        summary = summary[:247] + "…"
    if not summary:
        summary = f"Details about this {category} have been published by {source}."

    # 3. Remediation
    remediation_choice = _pick(
        REMEDIATIONS.get(category, REMEDIATIONS["news"]), seed=title + category
    )

    # 4. Hashtags
    hashtags = _build_hashtags(category, title)

    # 5. Format
    template = TEMPLATES.get(category, TEMPLATES["news"])
    caption = template.format(
        hook=hook,
        summary=summary,
        remediation=remediation_choice,
        hashtags=hashtags,
        url=url,
    )

    # Append author line
    caption += f"\n\n{BRAND['author_line']}"
    return caption.strip()


def generate_ai(item: dict[str, Any], config: dict[str, Any]) -> str:
    """
    Generate caption via Claude or HuggingFace API.

    Falls back to template on any error.

    Config keys:
        ai_backend:   "claude" | "huggingface"
        claude_api_key, hf_api_token, hf_model_id
    """
    try:
        if config.get("ai_backend") == "claude":
            return _generate_claude(item, config)
        elif config.get("ai_backend") == "huggingface":
            return _generate_hf(item, config)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "AI caption generation failed (%s); falling back to template.", exc
        )
    return generate_template(item)


def _build_prompt(item: dict[str, Any]) -> str:
    """Build the system+user prompt for AI caption generation."""
    brand_name = BRAND["brand_name"]
    brand_ht = BRAND["brand_hashtag"]
    hashtags_str = " ".join(BRAND["top_hashtags"][:6])
    author = BRAND["author_line"]
    skills = ", ".join(BRAND["knows_about"][:10])

    return f"""You are a cybersecurity social media expert writing a LinkedIn post for
{brand_name} ({author}).

Brand keywords to front-load: {brand_name}, cybersecurity, ethical hacking, penetration testing.
Top hashtags to use (pick 4-6): {hashtags_str}
Author skills context: {skills}

Write a LinkedIn post for the following security news item.
Strictly follow this SEO structure:
1. Hook line (≤1 sentence) — include primary keyword + year 2026
2. 1-2 sentence summary of what happened
3. 1 sentence remediation or action recommendation
4. 4-6 hashtags from the list above (always include {brand_ht})
5. Source URL reference

News item:
  Title      : {item.get('title', '')}
  Summary    : {item.get('description', '')[:400]}
  Category   : {item.get('category', 'news')}
  Source URL : {item.get('url', '')}

Reply with ONLY the formatted post text. No preamble. Length: 80-200 words."""


def _generate_claude(item: dict[str, Any], config: dict[str, Any]) -> str:
    """Call Anthropic Claude API (requires ANTHROPIC_API_KEY)."""
    import json
    import urllib.request

    prompt = _build_prompt(item)
    api_key = config["claude_api_key"]
    payload = json.dumps({
        "model": config.get("claude_model", "claude-haiku-4-5-20251001"),
        "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"].strip()


def _generate_hf(item: dict[str, Any], config: dict[str, Any]) -> str:
    """Call HuggingFace Inference API (free tier)."""
    import json
    import urllib.request

    prompt = _build_prompt(item)
    model = config.get("hf_model_id", "mistralai/Mistral-7B-Instruct-v0.2")
    token = config.get("hf_api_token", "")
    url = f"https://api-inference.huggingface.co/models/{model}"

    payload = json.dumps({"inputs": prompt, "parameters": {"max_new_tokens": 400}}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    if isinstance(data, list) and data:
        text = data[0].get("generated_text", "")
        # Strip echoed prompt
        if prompt in text:
            text = text[len(prompt):].strip()
        return text
    return generate_template(item)


def generate(item: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    """
    Public entry point.  Respects config['caption_backend']:
      "template" (default) or "ai".
    """
    cfg = config or {}
    if cfg.get("caption_backend") == "ai":
        return generate_ai(item, cfg)
    return generate_template(item)
