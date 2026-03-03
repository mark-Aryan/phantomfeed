# 🔐 PhantomFeed — Ghost in the machine. Signal in the noise.

**Automated 24×7 cybersecurity news → branded LinkedIn post generator**  
by **Aryan Kumar Upadhyay** ([@aryankrupadhyay](https://twitter.com/aryankrupadhyay)) · [codeXploit](https://codexploit.in) · `codexploit.in`

---

## What It Does

Continuously polls cybersecurity news sources (NewsAPI, NIST NVD/CVE, security RSS feeds), deduplicates items, classifies them, safety-filters for PoC content, then generates:

- **Branded LinkedIn captions** — SEO-optimised, front-loaded with `#codeXploit` and keywords from your `index.html`
- **LinkedIn-sized images** — 1200×627 or 1080×1080, with title overlay and watermark
- **Organised output folders** — `out/<category>/<YYYY-MM-DD>/<slug>-<id>/`

All items are persisted in a SQLite deduplication database so restarts never re-process content.

---

## Architecture

```
cyber-news-poster/
├── cli.py                    # CLI entry point (start/daemon/status/reprocess/purge/seed)
├── core.py                   # Orchestrator: run_cycle(), run_daemon()
│
├── fetcher/                  # Async data sources (aiohttp + backoff)
│   ├── newsapi_fetcher.py    # NewsAPI.org adapter
│   ├── nvd_fetcher.py        # NIST NVD CVE feed
│   └── rss_fetcher.py        # Multi-feed RSS (Krebs, THN, BleepingComputer…)
│
├── pipeline/                 # Data processing
│   ├── normalizer.py         # Canonical item format (strips HTML, parses dates)
│   ├── dedupe.py             # Deterministic canonical IDs + SQLite DB
│   ├── classifier.py         # Keyword → category (vulnerability/fraud/bug/incident/news)
│   └── safety_filter.py      # PoC/exploit detection → manual_review flag
│
├── generators/               # Asset creation
│   ├── text_generator.py     # Template & AI (Claude/HuggingFace) caption backends
│   └── image_generator.py    # PIL placeholder & remote API image backends
│
├── storage/                  # Output management
│   └── organiser.py          # Creates out/<cat>/<date>/<slug>/ and writes files
│
├── brand/
│   └── brand_config.py       # SEO tokens extracted from index.html
│
├── tests/                    # pytest unit tests
│   ├── test_pipeline.py      # dedupe, classifier, safety, normalizer, text gen
│   └── test_image_generator.py
│
├── prompts/
│   └── claude-prompt.txt     # Auditable AI prompts
│
├── SAFETY.md                 # Explicit redaction rules
├── config.example.json       # Full annotated config
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

### Data Flow

```
Sources (NewsAPI / NVD / RSS)
       │
       ▼ [async fetch with backoff]
   Normalizer  →  canonical dict
       │
       ▼ [canonical_id]
   DedupeDB    →  skip if processed
       │
       ▼ [classifier]
   Category    →  vulnerability / fraud / bug / incident / news
       │
       ▼ [safety_filter]
 ┌─────┴────────┐
 │ FLAGGED?     │
 │ → review.txt │
 │ → NO assets  │
 └─────┬────────┘
       │ SAFE
       ▼
 TextGenerator  →  SEO caption (template or AI)
       │
       ▼
 ImageGenerator →  PNG (PIL placeholder or remote API)
       │
       ▼
  Organiser     →  out/<cat>/<date>/<slug>/
                     ├── image.png
                     ├── image_raw.png
                     ├── post.txt
                     └── meta.json
```

---

## Quick Start (No API Keys Required)

```bash
# 1. Clone and install
git clone https://github.com/your-username/cyber-news-poster
cd cyber-news-poster
pip install -r requirements.txt

# 2. Copy config
cp config.example.json config.json
cp .env.example .env

# 3. Run seed test — generates sample output without any API keys
python cli.py seed

# Output:
# [generated  ] CVE-2026-1234 — Critical RCE in Apache HTTP Server 2.4
# [generated  ] Massive Phishing Campaign Targets Indian Banks (2026)
# [generated  ] Ransomware Group Claims Healthcare Provider Breach
# ✅ Seed complete. Check out/ for output.
```

---

## Setup — Free API Keys

### NewsAPI (100 req/day free)
1. Register at https://newsapi.org/register
2. Add to `.env`: `NEWSAPI_KEY=your_key`

### NIST NVD (no key required for basic use)
- Automatically enabled. Rate: 5 req/30s without key.
- Optional key at https://nvd.nist.gov/developers/request-an-api-key (50 req/30s)

### HuggingFace (free tier)
1. Create account at https://huggingface.co
2. Get token at https://huggingface.co/settings/tokens
3. Add to `.env`: `HF_API_TOKEN=hf_your_token`
4. In `config.json`: set `"ai_backend": "huggingface"` for captions or `"image_backend": "remote"` for images

### Anthropic Claude (richer captions)
1. Get API key at https://console.anthropic.com
2. Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-...`
3. In `config.json`: set `"caption_backend": "ai"` and `"ai_backend": "claude"`

---

## CLI Reference

```bash
# One fetch cycle (fetch → process → save)
python cli.py start

# 24×7 daemon (runs every poll_interval seconds)
python cli.py daemon

# Show DB stats and metrics
python cli.py status

# Seed with test items (no API keys needed)
python cli.py seed

# Force-reprocess a specific item (deletes from DB first)
python cli.py reprocess "cve:CVE-2026-1234"

# Purge entire DB (requires confirmation)
python cli.py purge

# Start health-check HTTP server only
python cli.py healthcheck

# Custom config path
python cli.py --config /path/to/my-config.json start

# Debug logging
python cli.py --loglevel DEBUG daemon
```

---

## Docker Deployment (24×7)

```bash
# 1. Create config
cp config.example.json config.json
# Edit config.json with your API keys

# 2. Create .env with secrets
cp .env.example .env
# Fill in API keys

# 3. Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Health check
curl http://localhost:8080/health

# Stop
docker-compose down
```

The container mounts `./out`, `./data`, and `./logs` for persistence.

---

## Output Structure

```
out/
├── vulnerability/
│   └── 2026-01-15/
│       └── cve-2026-1234-critical-rce-a1b2c3/
│           ├── image.png       ← Final branded image (1200×627)
│           ├── image_raw.png   ← Background only (no text)
│           ├── post.txt        ← LinkedIn caption + SEO meta
│           └── meta.json       ← Raw metadata + canonical ID
│
├── fraud/
│   └── 2026-01-16/
│       └── massive-phishing-campaign-d4e5f6/
│           └── ...
│
└── incident/
    └── 2026-01-17/
        └── ransomware-claims-healthcare-789abc/
            └── ...
```

### Sample post.txt Output

```
# codeXploit Security Post
# Title    : CVE-2026-1234 — Critical RCE in Apache HTTP Server 2.4
# Category : vulnerability
# Source   : NVD
# URL      : https://nvd.nist.gov/vuln/detail/CVE-2026-1234
# Generated: 2026-01-15T10:30:00+00:00
────────────────────────────────────────────────────────────

🚨 Critical cybersecurity alert (2026): CVE-2026-1234 — Critical RCE in Apache HTTP Server 2.4

A critical remote code execution vulnerability (CVSS 9.8) was disclosed in Apache HTTP
Server 2.4.x, allowing unauthenticated attackers to execute arbitrary code via a malformed
HTTP/2 request header.

✅ Apply the vendor patch immediately and test in staging first.

#codeXploit #CVE #vulnerability #infosec #patchnow #cybersecurity

🔗 https://nvd.nist.gov/vuln/detail/CVE-2026-1234

— Aryan Kumar Upadhyay (@aryankrupadhyay) | codeXploit · codexploit.in
```

---

## Deduplication — How It Works

```python
# Priority:
# 1. CVE ID in title/URL        → "cve:CVE-2026-1234"
# 2. URL hash                   → "url:a1b2c3d4e5f6g7h8"
# 3. title + time(minute) + src → "hash:deadbeef12345678"
```

Items are persisted in `data/dedupe.db`. Re-running the daemon **never** regenerates
content for already-processed IDs. Use `python cli.py reprocess <id>` to force re-generation.

**Similarity guard**: If a new item has title similarity > 0.92 (Jaccard) with an existing
item but a different URL, it's treated as a near-duplicate and skipped.

---

## SEO Caption Structure (Exact)

All generated captions follow this structure:

```
1. Hook line     ← primary keyword + "2026" (front-loaded for SEO)
2. Summary       ← 1-2 sentences: what happened (source-attributed)
3. Remediation   ← 1 concrete action line
4. Hashtags      ← 4-6 tags (always #codeXploit + category + brand tags)
5. Source URL    ← attribution link
6. Author line   ← Aryan Kumar Upadhyay | codeXploit | codexploit.in
```

Hashtags are sourced from `<meta name="keywords">` in `index.html` and mapped
to `BRAND["top_hashtags"]` in `brand/brand_config.py`.

---

## Safety & Ethics

See [SAFETY.md](SAFETY.md) for full policy.

**Items containing any of these are auto-quarantined (no caption/image generated):**
- Fenced code blocks (` ``` `)
- Shell commands / reverse shells
- `getshell`, `payload`, `PoC`, `proof-of-concept`
- Step-by-step exploit instructions
- Metasploit payload generation commands

Quarantined items get a `review.txt` explaining why. A human must run
`python cli.py reprocess <id>` to publish after review.

---

## Configuration Reference

| Key | Default | Description |
|---|---|---|
| `poll_interval` | 3600 | Seconds between fetch cycles |
| `nvd_hours_back` | 24 | Hours of NVD history to fetch |
| `caption_backend` | `"template"` | `"template"` or `"ai"` |
| `image_backend` | `"placeholder"` | `"placeholder"` or `"remote"` |
| `image_size` | `"linkedin"` | `"linkedin"` (1200×627) or `"square"` (1080×1080) |
| `similarity_threshold` | 0.92 | Fuzzy dedup threshold (0–1) |
| `ai_backend` | `"claude"` | `"claude"` or `"huggingface"` |
| `hf_model_id` | Mistral-7B | HuggingFace model for captions |
| `hf_image_model` | SD 2.1 | HuggingFace model for images |

---

## Running Tests

```bash
# Install test deps
pip install pytest pytest-asyncio

# Run all tests
pytest tests/ -v

# Run with coverage
pip install pytest-cov
pytest tests/ --cov=. --cov-report=term-missing
```

Expected output:
```
tests/test_pipeline.py::TestCanonicalId::test_cve_in_title PASSED
tests/test_pipeline.py::TestDedupeDB::test_persistence_across_restarts PASSED
tests/test_pipeline.py::TestDedupeDB::test_no_duplicate_on_second_run PASSED
tests/test_pipeline.py::TestSafetyFilter::test_code_block_flagged PASSED
tests/test_pipeline.py::TestTextGenerator::test_caption_contains_brand_hashtag PASSED
...
```

---

## Adding a GPU / Local Diffusers Backend

```python
# generators/image_generator.py — add this backend:

def generate_diffusers(item, out_dir, config, size):
    """Local GPU pipeline using HuggingFace diffusers."""
    from diffusers import StableDiffusionPipeline
    import torch

    pipe = StableDiffusionPipeline.from_pretrained(
        config.get("local_model_path", "runwayml/stable-diffusion-v1-5"),
        torch_dtype=torch.float16,
    ).to("cuda")
    # ... rest of generation
```

Set `"image_backend": "diffusers"` in `config.json` to enable.

---

## Brand Tokens (from index.html)

Extracted automatically from `index.html`:

| Field | Value |
|---|---|
| Brand | codeXploit |
| Person | Aryan Kumar Upadhyay |
| Job Title | Cybersecurity Analyst & Ethical Hacker |
| Website | codexploit.in |
| GitHub | github.com/mark-Aryan |
| LinkedIn | linkedin.com/in/aryan-kumar-upadhyay |
| Twitter | @aryankrupadhyay |
| Fiverr | fiverr.com/mark_aryan |
| Primary Hashtag | #codeXploit |

---

## License

MIT — © 2026 Aryan Kumar Upadhyay · codeXploit · codexploit.in
