"""
generators/deep_caption.py
===========================
UPGRADE #1 — In-depth caption generator.

Produces a structured, long-form LinkedIn post with:
  • What happened (detailed)
  • Why it matters / impact
  • How to fix / patch right now
  • How to prevent (proactive hardening steps)
  • Threat level badge
  • Deep technical context

Falls back gracefully to the original template backend.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from brand.brand_config import BRAND

# ─── Severity detection ────────────────────────────────────────────────────────
_CVSS_RE = re.compile(r"CVSS\s*(?:score\s*)?([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_CVE_RE  = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)

def _threat_level(title: str, desc: str) -> tuple[str, str]:
    """Return (emoji, label) based on severity signals."""
    corpus = (title + " " + desc).lower()
    cvss_m = _CVSS_RE.search(corpus)
    if cvss_m:
        score = float(cvss_m.group(1))
        if score >= 9.0: return "🔴", "CRITICAL"
        if score >= 7.0: return "🟠", "HIGH"
        if score >= 4.0: return "🟡", "MEDIUM"
        return "🟢", "LOW"
    for kw in ("critical", "rce", "remote code", "0day", "zero-day", "unauthenticated"):
        if kw in corpus: return "🔴", "CRITICAL"
    for kw in ("high", "privilege escalation", "auth bypass", "sql injection"):
        if kw in corpus: return "🟠", "HIGH"
    for kw in ("breach", "ransomware", "data leak", "phishing campaign"):
        if kw in corpus: return "🟠", "HIGH"
    return "🟡", "MEDIUM"

# ─── Category-specific fix/prevent knowledge base ──────────────────────────────
FIX_GUIDES: dict[str, dict[str, list[str]]] = {
    "vulnerability": {
        "fix": [
            "Apply the vendor security patch immediately — check {source} advisory for patch link.",
            "If patch is unavailable: restrict access to affected endpoint via firewall / WAF rule.",
            "Disable or sandbox the vulnerable component until a fix is released.",
            "Enable runtime protection (IDS/IPS signatures) targeting this CVE pattern.",
        ],
        "prevent": [
            "Maintain a real-time software inventory (SBOM) to detect vulnerable packages fast.",
            "Run weekly automated vulnerability scans (OpenVAS / Tenable / Qualys).",
            "Subscribe to vendor security mailing lists and NVD feeds for zero-day alerts.",
            "Adopt a patch SLA policy: Critical = 24 h, High = 72 h, Medium = 2 weeks.",
            "Segment critical services to limit blast radius of any future exploits.",
        ],
    },
    "incident": {
        "fix": [
            "Isolate affected systems immediately — pull network cable or disable NIC.",
            "Rotate ALL credentials (API keys, DB passwords, service accounts) used on compromised hosts.",
            "Engage your Incident Response team and preserve forensic artifacts (memory dumps, logs).",
            "Notify affected users / data protection authority within legally required window (72 h GDPR).",
        ],
        "prevent": [
            "Implement Zero Trust architecture — assume breach, verify every request.",
            "Deploy EDR/XDR on all endpoints for real-time threat detection.",
            "Conduct quarterly tabletop exercises simulating this exact attack scenario.",
            "Enforce MFA on every privileged account — TOTP minimum, FIDO2 preferred.",
            "Regular offline backups (3-2-1 rule) tested monthly for ransomware resilience.",
        ],
    },
    "fraud": {
        "fix": [
            "Block known phishing domains in DNS / email gateway — share IOCs with your team.",
            "Force password resets for any users who may have interacted with the campaign.",
            "Report phishing infrastructure to registrar / hosting provider for takedown.",
            "Issue a user advisory with screenshots of the fake page for awareness.",
        ],
        "prevent": [
            "Deploy DMARC + DKIM + SPF on all company email domains to prevent spoofing.",
            "Run simulated phishing campaigns monthly to train staff muscle memory.",
            "Enable browser-based phishing protection (Google Safe Browsing / Microsoft Defender SmartScreen).",
            "Use a password manager — eliminates password reuse across phishing-harvested sites.",
            "Enforce MFA so stolen credentials alone are useless to attackers.",
        ],
    },
    "bug": {
        "fix": [
            "Pin the patched version in your dependency manifest immediately.",
            "Run your full regression test suite after patching to catch side effects.",
            "Audit codebase for similar patterns using static analysis (Semgrep / SonarQube).",
        ],
        "prevent": [
            "Integrate SAST (static analysis) into your CI/CD pipeline — fail builds on critical findings.",
            "Use Dependabot / Renovate for automated dependency update PRs.",
            "Enforce code review with security checklist before merging to main.",
            "Fuzz-test critical parsing and input-handling functions regularly.",
        ],
    },
    "news": {
        "fix": [
            "Review your environment against the threat indicators mentioned in this report.",
            "Cross-reference with MITRE ATT&CK to understand relevant TTPs.",
            "Brief your security team on this development and update detection rules accordingly.",
        ],
        "prevent": [
            "Subscribe to threat intelligence feeds (CISA, US-CERT, vendor advisories).",
            "Map your defenses against the MITRE ATT&CK framework for coverage gaps.",
            "Adopt a continuous security posture review cycle — monthly minimum.",
            "Foster a security-first culture with regular awareness training.",
        ],
    },
}

def _pick(lst: list[str], seed: str = "") -> str:
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(lst)
    return lst[idx]

def _pick_n(lst: list[str], n: int, seed: str = "") -> list[str]:
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    result = []
    for i in range(n):
        result.append(lst[(idx + i) % len(lst)])
    return result

# ─── Deep template caption ─────────────────────────────────────────────────────

def generate_deep_template(item: dict[str, Any]) -> str:
    """
    Generates a rich, in-depth LinkedIn caption with:
     - Threat level badge
     - Detailed what/why/impact
     - Step-by-step fix actions
     - Proactive prevention checklist
     - Technical context
    """
    title       = item.get("title", "Security Update")
    description = item.get("description", "")
    category    = item.get("category", "news")
    url         = item.get("url", BRAND["website_url"])
    source      = item.get("source", "")

    emoji, level = _threat_level(title, description)
    cve_m = _CVE_RE.search(title + " " + url)
    cve_id = cve_m.group(0).upper() if cve_m else None

    guide = FIX_GUIDES.get(category, FIX_GUIDES["news"])
    fix_steps    = _pick_n(guide["fix"],     min(3, len(guide["fix"])),     seed=title)
    prev_steps   = _pick_n(guide["prevent"], min(4, len(guide["prevent"])), seed=title + "prev")

    # Build sentences
    sentences = re.split(r"(?<=[.!?])\s+", description.strip())
    what = " ".join(sentences[:3]) if sentences else f"Details about this {category} have been published by {source}."
    if len(what) > 400:
        what = what[:397] + "…"

    # CVE context line
    cve_line = f"\n🔎 CVE Reference: {cve_id}" if cve_id else ""

    fix_block  = "\n".join(f"  {'①②③④⑤'[i]} {s}" for i, s in enumerate(fix_steps))
    prev_block = "\n".join(f"  {'◆◇▸▹▪'[i]} {s.format(source=source)}" for i, s in enumerate(prev_steps))

    # Hashtags (reuse existing builder)
    from generators.text_generator import _build_hashtags
    hashtags = _build_hashtags(category, title)

    caption = f"""{emoji} [{level}] {title}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{cve_line}

📋 WHAT HAPPENED
{what}

⚡ WHY THIS MATTERS
{"Attackers can exploit this to gain unauthorized access, exfiltrate data, or disrupt operations." if category in ("vulnerability","incident") else "This type of threat directly impacts users, organizations, and digital trust at scale."}

🔧 HOW TO FIX (RIGHT NOW)
{fix_block}

🛡️ HOW TO PREVENT (LONG-TERM)
{prev_block}

{hashtags}

🔗 Source: {url}

{BRAND['author_line']}"""

    return caption.strip()


# ─── Deep AI caption (Claude) ─────────────────────────────────────────────────

def _build_deep_prompt(item: dict[str, Any]) -> str:
    title    = item.get("title", "")
    desc     = item.get("description", "")
    category = item.get("category", "news")
    url      = item.get("url", "")
    source   = item.get("source", "")

    brand_name = BRAND["brand_name"]
    author     = BRAND["author_line"]
    hashtags   = " ".join(BRAND["top_hashtags"][:6])
    _, level   = _threat_level(title, desc)

    return f"""You are a senior cybersecurity analyst writing a detailed LinkedIn post for {brand_name}.
Author: {author}
Threat Level Detected: {level}

Write a comprehensive, in-depth LinkedIn post about the following security news.
Your post MUST contain ALL of these sections in order:

1. 🔴/🟠/🟡 [THREAT LEVEL] + Title (1 line hook)
2. 📋 WHAT HAPPENED — 3-4 detailed sentences explaining the technical specifics
3. ⚡ WHY THIS MATTERS — Impact on organizations, severity, attack surface
4. 🔧 HOW TO FIX IT RIGHT NOW — 3 specific, actionable remediation steps (numbered)
5. 🛡️ HOW TO PREVENT THIS — 3-4 proactive hardening recommendations (bulleted)
6. Technical context (CVE IDs, CVSS scores, affected versions if present in input)
7. 4-6 hashtags (always include #codeXploit): {hashtags}
8. Source URL: {url}
9. Author line: {author}

News item:
  Title   : {title}
  Summary : {desc[:600]}
  Category: {category}
  Source  : {source}
  URL     : {url}

Write ONLY the post. No preamble. Target length: 200-350 words.
Make the FIX and PREVENT sections genuinely useful and technical."""


def generate_deep_ai(item: dict[str, Any], config: dict[str, Any]) -> str:
    """Call Claude for deep analysis caption. Falls back to deep template."""
    try:
        if config.get("ai_backend", "claude") == "claude" and config.get("claude_api_key"):
            return _call_claude_deep(item, config)
        elif config.get("ai_backend") == "huggingface" and config.get("hf_api_token"):
            return _call_hf_deep(item, config)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Deep AI caption failed (%s); using deep template.", exc)
    return generate_deep_template(item)


def _call_claude_deep(item: dict[str, Any], config: dict[str, Any]) -> str:
    import json, urllib.request
    prompt  = _build_deep_prompt(item)
    payload = json.dumps({
        "model": config.get("claude_model", "claude-haiku-4-5-20251001"),
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": config["claude_api_key"],
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"].strip()


def _call_hf_deep(item: dict[str, Any], config: dict[str, Any]) -> str:
    import json, urllib.request
    prompt = _build_deep_prompt(item)
    model  = config.get("hf_model_id", "mistralai/Mistral-7B-Instruct-v0.2")
    token  = config.get("hf_api_token", "")
    payload = json.dumps({"inputs": prompt, "parameters": {"max_new_tokens": 700}}).encode()
    req = urllib.request.Request(
        f"https://api-inference.huggingface.co/models/{model}",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read())
    if isinstance(data, list) and data:
        text = data[0].get("generated_text", "")
        if prompt in text:
            text = text[len(prompt):].strip()
        return text
    return generate_deep_template(item)


def generate(item: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    """
    Public entry point.
    Config key 'caption_depth': 'deep' (default) | 'standard'
    Config key 'caption_backend': 'ai' | 'template'
    """
    cfg = config or {}
    depth   = cfg.get("caption_depth", "deep")
    backend = cfg.get("caption_backend", "template")

    if depth == "standard":
        from generators.text_generator import generate as std_generate
        return std_generate(item, cfg)

    if backend == "ai":
        return generate_deep_ai(item, cfg)
    return generate_deep_template(item)
