# SAFETY.md — codeXploit Cyber News Poster
## Security & Ethics Policy — Exploit Redaction Rules

---

## Principle

This tool generates **public-facing LinkedIn content** about cybersecurity news.
It must NEVER auto-publish:

- Proof-of-concept (PoC) exploit code
- Step-by-step attack walkthroughs
- Shell commands that enable exploitation  
- Payloads, shellcode, or ready-to-use attack strings

All such items are **flagged for manual review** and quarantined in a `review.txt` file.

---

## Detection Rules (pipeline/safety_filter.py)

The following patterns trigger the `manual_review` flag:

| Pattern | Rationale |
|---|---|
| ` ``` ` (fenced code blocks) | Likely contains exploit code |
| `<code>` HTML tags | Embedded code in articles |
| `$ command` (shell prompt) | Step-by-step shell instructions |
| `getshell` | Exploitation success term |
| `payload` | Attack payload delivery |
| `exploit.py` | Named exploit script |
| `PoC` / `proof-of-concept` | Explicit exploit labelling |
| `step-by-step exploit` | Walkthrough language |
| `how to exploit` | Direct enablement |
| `msfvenom`, `metasploit use` | MSF payload generation |
| `shellcode` | Raw machine-code exploits |
| `nc -e` (netcat reverse shell) | Remote shell setup |
| `bash -i >&` (bash reverse shell) | Reverse shell one-liner |
| `python -c 'import socket` | Python reverse shell |
| `curl ... \| bash` | Pipe-to-shell attacks |
| `wget -O - ... \| sh` | Wget-to-shell attacks |
| `step N: run/execute/upload` | Multi-step exploit instructions |
| `full exploit code/walkthrough` | Complete exploit disclosure |

---

## What Happens When an Item Is Flagged

1. **No caption is generated.** 
2. **No image is generated.**
3. A `review.txt` is written to `out/<category>/<date>/<slug>/review.txt` explaining:
   - Which patterns matched
   - The source URL for human inspection
4. A `meta.json` is written for record-keeping.
5. The item is marked `flagged=1` in the SQLite DB.

---

## Reviewer Process

After a human reviews a flagged item:

**If safe to publish** (e.g., pure vendor advisory, no PoC):
```bash
python cli.py reprocess "cve:CVE-2026-XXXX"
python cli.py start
```

**If it contains exploit details**: Do not publish. Archive the folder.

---

## Redaction (for safe preview in review.txt)

`pipeline/safety_filter.py::redact()` strips:
- Fenced code blocks (` ``` ... ``` `) → `[CODE REDACTED]`
- Inline backticks → `[CODE REDACTED]`  
- HTML `<code>` blocks → `[CODE REDACTED]`

This is used ONLY in the `review.txt` preview, never in published content.

---

## Adding New Redaction Rules

Add a regex pattern to `REDACTION_PATTERNS` list in `pipeline/safety_filter.py`:

```python
REDACTION_PATTERNS = [
    ...
    r"(?i)\byour_new_pattern\b",   # Add here with comment
]
```

Every pattern change must be documented here in `SAFETY.md`.

---

## Limitations

This is a **keyword/pattern-based heuristic**, not a semantic AI classifier.
It will produce:
- **False positives**: Legitimate articles mentioning "payload" in a research context
- **False negatives**: Novel exploit writeups using different terminology

**Human review is the final safety gate.** This tool reduces workload; it does
not replace judgment.

---

## Compliance

- This project follows responsible disclosure principles.
- It does not scrape or republish paid/paywalled security research.
- All content is attributed to its original source.
- Brand and contact: codeXploit | Aryan Kumar Upadhyay | codexploit.in
