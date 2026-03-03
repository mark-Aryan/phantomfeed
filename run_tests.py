#!/usr/bin/env python3
"""
run_tests.py — offline test runner (no pytest/network needed)
"""
import sys, types, tempfile, json
from pathlib import Path

# ── Mock unavailable packages ─────────────────────────────────────────────────
for mod_name in ['aiohttp', 'feedparser']:
    m = types.ModuleType(mod_name)
    if mod_name == 'aiohttp':
        m.ClientSession = object
        m.ClientError = Exception
        m.TCPConnector = object
        m.ClientTimeout = object
    sys.modules[mod_name] = m

dotenv_mod = types.ModuleType('dotenv')
dotenv_mod.load_dotenv = lambda: None
sys.modules['dotenv'] = dotenv_mod

sys.path.insert(0, '.')

from pipeline.dedupe import canonical_id, similarity, slugify, DedupeDB
from pipeline.classifier import classify
from pipeline.safety_filter import check, redact
from pipeline.normalizer import normalize_newsapi
from generators.text_generator import generate_template, _build_hashtags
from brand.brand_config import BRAND
from storage.organiser import item_dir, save_post, save_meta
from generators.image_generator import generate_placeholder
try:
    from PIL import Image as PILImage
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ── Test helpers ──────────────────────────────────────────────────────────────
passed = 0
failed = 0

def eq(a, b):
    assert a == b, "%r != %r" % (a, b)

def sw(s, p):
    assert s.startswith(p), "%r does not start with %r" % (s, p)

def test(name, fn):
    global passed, failed
    try:
        fn()
        print("  PASS  " + name)
        passed += 1
    except Exception as e:
        print("  FAIL  " + name + ": " + str(e))
        failed += 1

# ── Dedupe ────────────────────────────────────────────────────────────────────
print("\n--- Dedupe ---")
test("cve_title", lambda: eq(canonical_id(title="CVE-2026-1234 RCE"), "cve:CVE-2026-1234"))
test("cve_lowercase", lambda: eq(canonical_id(title="cve-2026-9999 bug"), "cve:CVE-2026-9999"))
test("url_hash", lambda: sw(canonical_id(url="https://x.com/a"), "url:"))
test("url_slash_norm", lambda: eq(
    canonical_id(url="https://x.com/a/"),
    canonical_id(url="https://x.com/a"),
))
test("fallback_hash", lambda: sw(
    canonical_id(title="T", published_at="2026-01-01T12:00:01Z", source="s"), "hash:"
))
test("deterministic_minute", lambda: eq(
    canonical_id(title="T", published_at="2026-01-01T12:05:01Z", source="s"),
    canonical_id(title="T", published_at="2026-01-01T12:05:59Z", source="s"),
))
test("similarity_1.0", lambda: eq(similarity("hello world", "hello world"), 1.0))
test("similarity_0.0", lambda: eq(similarity("", "anything"), 0.0))
test("slugify_basic", lambda: eq(slugify("Hello World!"), "hello-world"))
test("slugify_maxlen", lambda: eq(len(slugify("a" * 100, 20)) <= 20, True))
test("similarity_partial", lambda: eq(similarity("CVE in Apache", "Apache vulnerability") > 0, True))

# DB
print("\n--- DedupeDB ---")
with tempfile.TemporaryDirectory() as td:
    db_path = Path(td) / "p.db"
    db1 = DedupeDB(db_path)
    db1.mark_processed(canonical_id="url:0000000000000001", slug="s")
    db1.close()

    db2 = DedupeDB(db_path)
    test("db_persist", lambda: eq(db2.is_processed("url:0000000000000001"), True))
    # Second run should still return True (no reprocessing)
    test("db_no_reprocess", lambda: eq(db2.is_processed("url:0000000000000001"), True))
    test("db_delete", lambda: eq(db2.delete("url:0000000000000001"), True))
    test("db_after_delete", lambda: eq(db2.is_processed("url:0000000000000001"), False))
    db2.mark_processed(canonical_id="url:1111111111111111", slug="s", category="vulnerability")
    db2.mark_processed(canonical_id="url:2222222222222222", slug="t", category="incident")
    stats = db2.stats()
    test("db_stats_total", lambda: eq(stats["total"], 2))
    n = db2.purge()
    test("db_purge", lambda: eq(n, 2))
    db2.close()

# ── Classifier ────────────────────────────────────────────────────────────────
print("\n--- Classifier ---")
test("class_cve", lambda: eq(classify("CVE-2026-1234 critical RCE"), "vulnerability"))
test("class_phishing", lambda: eq(classify("Large phishing campaign targets banks"), "fraud"))
test("class_ransomware", lambda: eq(classify("Ransomware attack hits hospital"), "incident"))
test("class_news", lambda: eq(classify("New cybersecurity framework announced"), "news"))
test("class_bug", lambda: eq(classify("Memory leak bug causes crash in Firefox"), "bug"))
test("class_xss", lambda: eq(classify("XSS vulnerability in WordPress plugin"), "vulnerability"))
test("class_breach", lambda: eq(classify("Data breach exposes millions of records"), "incident"))
test("class_case_insensitive", lambda: eq(classify("CRITICAL VULNERABILITY IN OPENSSL"), "vulnerability"))

# ── Safety Filter ─────────────────────────────────────────────────────────────
print("\n--- Safety Filter ---")
safe = {"title": "Apache patches CVE", "description": "Vendor fix released.", "content": ""}
poc = {"title": "Exploit", "description": "PoC code: ```os.system('id')```", "content": ""}
getshell_item = {"title": "X", "description": "Attacker can getshell via endpoint.", "content": ""}
test("safety_clean", lambda: eq(check(safe).is_safe, True))
test("safety_poc", lambda: eq(check(poc).is_safe, False))
test("safety_getshell", lambda: eq(check(getshell_item).is_safe, False))
test("safety_reasons_populated", lambda: eq(len(check(poc).reasons) > 0, True))
test("redact_code", lambda: eq("CODE REDACTED" in redact("Use ```code``` here"), True))

# ── Normalizer ────────────────────────────────────────────────────────────────
print("\n--- Normalizer ---")
raw_news = {
    "title": "<b>News Item</b>", "description": "<p>Article content</p>",
    "url": "https://example.com/news", "publishedAt": "2026-01-01T10:00:00Z",
    "source": {"name": "Example"},
}
item = normalize_newsapi(raw_news)
test("norm_strips_html", lambda: eq("<" not in item["title"], True))
test("norm_url", lambda: eq(item["url"], "https://example.com/news"))
test("norm_source", lambda: eq(item["source"], "Example"))

# ── Text Generator ────────────────────────────────────────────────────────────
print("\n--- Text Generator ---")
ti = {
    "title": "CVE-2026-1234 critical RCE in Apache",
    "description": "Critical vulnerability in Apache 2.4.x allows RCE.",
    "category": "vulnerability",
    "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-1234",
    "source": "NVD",
}
cap = generate_template(ti)
test("cap_brand_hashtag", lambda: eq("#codeXploit" in cap, True))
test("cap_year_2026", lambda: eq("2026" in cap, True))
test("cap_cve_id", lambda: eq("CVE-2026-1234" in cap, True))
test("cap_url", lambda: eq("nvd.nist.gov" in cap, True))
test("cap_deterministic", lambda: eq(generate_template(ti), generate_template(ti)))
test("cap_length_ok", lambda: eq(40 <= len(cap.split()) <= 300, True))
test("cap_author_line", lambda: eq("Aryan Kumar Upadhyay" in cap or "codexploit.in" in cap, True))

fi = {"title": "Phishing hits banks", "description": "Campaign detected.", "category": "fraud", "url": "https://x.com", "source": "X"}
cap_fraud = generate_template(fi)
test("fraud_caption_brand", lambda: eq("#codeXploit" in cap_fraud, True))

tags = _build_hashtags("vulnerability", "CVE-2026-1")
seen = set()
dupes = False
for t in tags.split():
    if t.lower() in seen:
        dupes = True
    seen.add(t.lower())
test("tags_no_dupes", lambda: eq(dupes, False))
test("tags_max6", lambda: eq(len(tags.split()) <= 6, True))
test("tags_has_brand", lambda: eq("#codeXploit" in tags, True))

# ── Brand Config ──────────────────────────────────────────────────────────────
print("\n--- Brand Config ---")
required_keys = ["page_title", "person_name", "job_title", "brand_hashtag",
                 "top_hashtags", "watermark_text", "same_as", "knows_about"]
for k in required_keys:
    test("brand_has_" + k, lambda k=k: eq(k in BRAND, True))
test("brand_hashtag_fmt", lambda: eq(BRAND["brand_hashtag"].startswith("#"), True))
test("brand_person_name", lambda: eq(BRAND["person_name"], "Aryan Kumar Upadhyay"))
test("brand_website", lambda: eq("codexploit.in" in BRAND["website_url"], True))

# ── Organiser ─────────────────────────────────────────────────────────────────
print("\n--- Organiser ---")
with tempfile.TemporaryDirectory() as td:
    oi = {
        "title": "Test Security Alert about Vulnerability",
        "description": "X", "url": "https://example.com",
        "published_at": "2026-01-15T10:00:00Z",
        "source": "T", "category": "vulnerability",
    }
    d = item_dir(td, oi, "cve:CVE-2026-T")
    test("org_category_dir", lambda: eq(d.parts[-3], "vulnerability"))
    test("org_date_dir", lambda: eq(d.parts[-2], "2026-01-15"))
    d1 = item_dir(td, oi, "cve:CVE-2026-A")
    d2 = item_dir(td, oi, "cve:CVE-2026-B")
    test("org_no_slug_collision", lambda: eq(d1 != d2, True))
    pp = save_post(d, "Caption #codeXploit", oi)
    test("post_exists", lambda: eq(pp.exists(), True))
    test("post_brand", lambda: eq("#codeXploit" in pp.read_text(), True))
    mp = save_meta(d, oi, "cve:CVE-2026-T")
    test("meta_valid_json", lambda: eq(json.loads(mp.read_text())["canonical_id"], "cve:CVE-2026-T"))

# ── Image Generator ───────────────────────────────────────────────────────────
print("\n--- Image Generator ---")
if PIL_OK:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        raw_p, fin_p = generate_placeholder(ti, out)
        test("img_raw_exists", lambda: eq(raw_p.exists(), True))
        test("img_final_exists", lambda: eq(fin_p.exists(), True))
        test("img_size_ok", lambda: eq(fin_p.stat().st_size > 5000, True))
        with PILImage.open(fin_p) as img:
            w, h = img.size
        test("img_linkedin_dims", lambda: eq((w, h), (1200, 627)))
        # Square size
        out2 = Path(td) / "sq"
        out2.mkdir()
        _, sq = generate_placeholder(ti, out2, size=(1080, 1080))
        with PILImage.open(sq) as img2:
            test("img_square_dims", lambda: eq(img2.size, (1080, 1080)))
        # All categories
        for cat in ["vulnerability", "fraud", "bug", "incident", "news"]:
            cat_out = Path(td) / cat
            cat_out.mkdir()
            _, fp = generate_placeholder({**ti, "category": cat}, cat_out)
            test("img_cat_" + cat, lambda fp=fp: eq(fp.exists(), True))
else:
    print("  SKIP  image tests (Pillow not available)")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Results: %d passed, %d failed" % (passed, failed))
if failed:
    sys.exit(1)
else:
    print("All tests passed! ✅")
