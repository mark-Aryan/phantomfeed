"""
brand/brand_config.py
=====================
Canonical SEO & brand tokens extracted from index.html.
All caption templates, hashtag selectors, and image watermarks
pull from BRAND (or from a config.json override).

HUMAN REVIEW: If index.html changes, re-run:
    python -m brand.brand_config --html path/to/index.html
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ── Tokens hard-coded from the live index.html ────────────────────────────────
BRAND: dict[str, Any] = {
    "page_title": (
        "codeXploit | Aryan Kumar Upadhyay – "
        "Cybersecurity Analyst & Ethical Hacker India"
    ),
    "meta_description": (
        "codeXploit is the official portfolio of Aryan Kumar Upadhyay — "
        "Cybersecurity Analyst, Ethical Hacker, Penetration Tester & "
        "Full-Stack Developer from India. 3+ years protecting organizations "
        "with expert vulnerability assessment, network security & security consulting."
    ),
    "meta_keywords": [
        "codeXploit", "cybersecurity analyst India", "ethical hacker India",
        "penetration tester India", "vulnerability assessment India",
        "network security expert", "web application security",
        "Python security tools", "Django developer India",
        "Aryan Kumar Upadhyay", "bug bounty hunter India", "OWASP Top 10",
        "red team India", "SQL injection tester", "kali linux hacker",
        "metasploit", "burp suite expert", "infosec",
    ],
    "person_name": "Aryan Kumar Upadhyay",
    "alternate_names": [
        "Aryan Upadhyay", "mark aryan", "mark-aryan",
        "codeXploit", "codexploit", "CodeXploit", "Codxploit",
        "codxploit", "aryankumarupadhyay",
    ],
    "job_title": "Cybersecurity Analyst & Ethical Hacker",
    "website_url": "https://codexploit.in/",
    "same_as": [
        "https://codexploit.in/",
        "https://github.com/mark-Aryan",
        "https://www.linkedin.com/in/aryan-kumar-upadhyay",
        "https://twitter.com/aryankrupadhyay",
        "https://www.fiverr.com/mark_aryan",
        "https://coursexploit.netlify.app",
    ],
    "knows_about": [
        "Cybersecurity", "Ethical Hacking", "Penetration Testing",
        "Network Security", "Vulnerability Assessment", "Incident Response",
        "Threat Detection", "SQL Injection", "Web Application Security",
        "OWASP Top 10", "Red Teaming", "Bug Bounty", "Kali Linux",
        "Python", "Django", "Web Development", "Full-Stack Development",
        "Nmap", "Metasploit", "Wireshark", "Burp Suite", "Bash Scripting",
        "ARP Spoofing", "Packet Sniffing", "MAC Address Changing",
    ],
    "brand_name": "codeXploit",
    "brand_hashtag": "#codeXploit",
    "watermark_text": "codeXploit | codexploit.in",
    "top_hashtags": [
        "#codeXploit", "#cybersecurity", "#ethicalhacking", "#infosec",
        "#penetrationtesting", "#CVE", "#bugbounty", "#Python",
        "#vulnerabilityassessment", "#networksecurity", "#patchnow", "#OWASP",
    ],
    "cta_options": [
        "Patch now — don't wait for threat actors.",
        "Review your logs and harden your systems today.",
        "Contact your security team immediately.",
        "Run a vulnerability scan with codeXploit tools at codexploit.in",
        "Share this alert with your security team.",
    ],
    "author_line": (
        "— Aryan Kumar Upadhyay (@aryankrupadhyay) | "
        "codeXploit · codexploit.in"
    ),
}


def load_from_html(html_path: str | Path) -> dict[str, Any]:
    """Parse index.html and return brand tokens, falling back to BRAND defaults."""
    path = Path(html_path)
    if not path.exists():
        return BRAND.copy()

    html = path.read_text(encoding="utf-8", errors="replace")
    result: dict[str, Any] = BRAND.copy()

    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        result["page_title"] = m.group(1).strip()

    m = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        html, re.IGNORECASE,
    )
    if m:
        result["meta_description"] = m.group(1).strip()

    m = re.search(
        r'<meta\s+name=["\']keywords["\']\s+content=["\'](.*?)["\']',
        html, re.IGNORECASE,
    )
    if m:
        kws = [k.strip() for k in m.group(1).split(",") if k.strip()]
        if kws:
            result["meta_keywords"] = kws

    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.IGNORECASE | re.DOTALL,
    ):
        try:
            _extract_jsonld(json.loads(block.strip()), result)
        except (json.JSONDecodeError, ValueError):
            pass

    # Rebuild top_hashtags
    seen: set[str] = set()
    tags: list[str] = []
    for kw in result["meta_keywords"][:12]:
        tag = "#" + re.sub(r"[\s\-]+", "", kw.replace("#", ""))
        low = tag.lower()
        if low not in seen:
            seen.add(low)
            tags.append(tag)
    result["top_hashtags"] = tags[:12]
    return result


def _extract_jsonld(data: Any, result: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        return
    if data.get("@type") == "Person":
        for key, field in [
            ("name", "person_name"), ("jobTitle", "job_title"),
            ("url", "website_url"), ("sameAs", "same_as"),
            ("knowsAbout", "knows_about"), ("alternateName", "alternate_names"),
        ]:
            if key in data:
                val = data[key]
                result[field] = val if isinstance(val, list) else val


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="index.html")
    args = ap.parse_args()
    print(json.dumps(load_from_html(args.html), indent=2, default=str))
