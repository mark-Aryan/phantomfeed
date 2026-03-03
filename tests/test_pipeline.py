"""
tests/test_pipeline.py
=======================
Unit tests for: dedupe, slugify, classifier, safety_filter,
normalizer, text_generator (template mode).
Run: pytest tests/ -v
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# ── Dedupe tests ──────────────────────────────────────────────────────────────

from pipeline.dedupe import canonical_id, similarity, slugify, DedupeDB


class TestCanonicalId:
    def test_cve_in_title(self):
        cid = canonical_id(title="CVE-2026-1234 critical RCE")
        assert cid == "cve:CVE-2026-1234"

    def test_cve_uppercase_normalised(self):
        cid = canonical_id(title="cve-2026-9999 vulnerability")
        assert cid == "cve:CVE-2026-9999"

    def test_url_hash(self):
        cid = canonical_id(url="https://example.com/article/123")
        assert cid.startswith("url:")
        assert len(cid) == 4 + 16  # "url:" + 16 hex chars

    def test_url_trailing_slash_normalised(self):
        cid1 = canonical_id(url="https://example.com/article/")
        cid2 = canonical_id(url="https://example.com/article")
        assert cid1 == cid2

    def test_fallback_hash(self):
        cid = canonical_id(title="Some article", published_at="2026-01-01T12:05:00Z", source="test")
        assert cid.startswith("hash:")

    def test_deterministic_fallback(self):
        """Same inputs → same canonical ID (across calls)."""
        cid1 = canonical_id(title="Same title", published_at="2026-01-01T12:05:00Z", source="src")
        cid2 = canonical_id(title="Same title", published_at="2026-01-01T12:05:00Z", source="src")
        assert cid1 == cid2

    def test_fallback_truncates_time_to_minute(self):
        """Seconds should not affect the hash (truncated to minute)."""
        cid1 = canonical_id(title="X", published_at="2026-01-01T12:05:01Z", source="s")
        cid2 = canonical_id(title="X", published_at="2026-01-01T12:05:59Z", source="s")
        assert cid1 == cid2

    def test_cve_in_url(self):
        cid = canonical_id(url="https://nvd.nist.gov/CVE-2025-9876")
        assert cid == "cve:CVE-2025-9876"


class TestSimilarity:
    def test_identical(self):
        assert similarity("hello world", "hello world") == 1.0

    def test_disjoint(self):
        assert similarity("apple orange", "banana grape") == 0.0

    def test_partial(self):
        s = similarity("critical vulnerability in apache", "vulnerability in apache http")
        assert 0.0 < s < 1.0

    def test_threshold_pass(self):
        a = "Apache HTTP Server remote code execution vulnerability disclosed"
        b = "Apache HTTP Server remote code execution vulnerability reported"
        assert similarity(a, b) > 0.85

    def test_empty(self):
        assert similarity("", "anything") == 0.0


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World!") == "hello-world"

    def test_special_chars(self):
        assert slugify("CVE-2026-1234: RCE in Apache") == "cve-2026-1234-rce-in-apache"

    def test_max_length(self):
        long_text = "a" * 100
        assert len(slugify(long_text, max_len=20)) <= 20

    def test_unicode_stripped(self):
        slug = slugify("Héllo Wörld")
        assert "h" in slug
        assert "e" in slug


class TestDedupeDB:
    def test_mark_and_check(self, tmp_path):
        db = DedupeDB(tmp_path / "test.db")
        cid = "cve:CVE-2026-TEST"
        assert not db.is_processed(cid)
        db.mark_processed(canonical_id=cid, slug="test-slug")
        assert db.is_processed(cid)
        db.close()

    def test_ignore_duplicate_insert(self, tmp_path):
        db = DedupeDB(tmp_path / "test.db")
        cid = "url:abc123"
        db.mark_processed(canonical_id=cid, slug="slug1")
        db.mark_processed(canonical_id=cid, slug="slug2")  # Should not raise
        assert db.is_processed(cid)
        db.close()

    def test_delete(self, tmp_path):
        db = DedupeDB(tmp_path / "test.db")
        cid = "hash:deadbeef"
        db.mark_processed(canonical_id=cid, slug="s")
        assert db.delete(cid) is True
        assert not db.is_processed(cid)
        db.close()

    def test_purge(self, tmp_path):
        db = DedupeDB(tmp_path / "test.db")
        for i in range(5):
            db.mark_processed(canonical_id=f"url:{i:016d}", slug=f"slug{i}")
        n = db.purge()
        assert n == 5
        db.close()

    def test_persistence_across_restarts(self, tmp_path):
        """Marking an item and re-opening the DB should still show it processed."""
        db_path = tmp_path / "persist.db"
        db1 = DedupeDB(db_path)
        db1.mark_processed(canonical_id="url:abcdef0123456789", slug="s")
        db1.close()

        db2 = DedupeDB(db_path)
        assert db2.is_processed("url:abcdef0123456789")
        db2.close()

    def test_no_duplicate_on_second_run(self, tmp_path):
        """Simulates two runs; second run should skip already-processed item."""
        db_path = tmp_path / "dup.db"
        cid = "url:0000000000000001"

        # First run
        db = DedupeDB(db_path)
        assert not db.is_processed(cid)
        db.mark_processed(canonical_id=cid, slug="s")
        db.close()

        # Second run
        db = DedupeDB(db_path)
        assert db.is_processed(cid)  # Must be True — no re-processing
        db.close()

    def test_stats(self, tmp_path):
        db = DedupeDB(tmp_path / "stats.db")
        db.mark_processed(canonical_id="cve:CVE-2026-1", slug="s", category="vulnerability")
        db.mark_processed(canonical_id="url:111111111111111a", slug="t", category="incident")
        stats = db.stats()
        assert stats["total"] == 2
        db.close()


# ── Classifier tests ──────────────────────────────────────────────────────────

from pipeline.classifier import classify


class TestClassifier:
    def test_cve_is_vulnerability(self):
        assert classify("CVE-2026-1234 critical RCE") == "vulnerability"

    def test_phishing_is_fraud(self):
        assert classify("Large phishing campaign targets banks") == "fraud"

    def test_ransomware_is_incident(self):
        assert classify("Ransomware attack hits hospital") == "incident"

    def test_breach_is_incident(self):
        assert classify("Data breach exposes 10M records") == "incident"

    def test_bug_category(self):
        # needs 2 bug keywords
        assert classify("Memory leak bug causes crash in Firefox") == "bug"

    def test_default_to_news(self):
        assert classify("US announces new cybersecurity framework") == "news"

    def test_case_insensitive(self):
        assert classify("CRITICAL VULNERABILITY IN OPENSSL") == "vulnerability"

    def test_xss_vulnerability(self):
        assert classify("Reflected XSS vulnerability in WordPress plugin") == "vulnerability"


# ── Safety filter tests ───────────────────────────────────────────────────────

from pipeline.safety_filter import check, redact


class TestSafetyFilter:
    def _item(self, **kw):
        return {"title": "", "description": "", "content": "", **kw}

    def test_safe_item(self):
        result = check(self._item(
            title="Apache patches critical RCE vulnerability",
            description="Apache released a patch for CVE-2026-1234.",
        ))
        assert result.is_safe

    def test_code_block_flagged(self):
        result = check(self._item(
            description="Here is the PoC: ```python\nimport os; os.system('id')\n```",
        ))
        assert not result.is_safe
        assert len(result.reasons) > 0

    def test_getshell_flagged(self):
        result = check(self._item(description="Attacker can getshell via this endpoint."))
        assert not result.is_safe

    def test_payload_flagged(self):
        result = check(self._item(description="Send this payload to trigger the bug."))
        assert not result.is_safe

    def test_redact_code_blocks(self):
        text = "Use ```import os; os.system('id')``` to exploit."
        out = redact(text)
        assert "```" not in out
        assert "CODE REDACTED" in out


# ── Normalizer tests ──────────────────────────────────────────────────────────

from pipeline.normalizer import normalize_newsapi, normalize_nvd, normalize_rss


class TestNormalizer:
    def test_newsapi_basic(self):
        raw = {
            "title": "Security News",
            "description": "An article",
            "url": "https://example.com/a",
            "publishedAt": "2026-01-01T10:00:00Z",
            "source": {"name": "Example"},
        }
        item = normalize_newsapi(raw)
        assert item["title"] == "Security News"
        assert item["url"] == "https://example.com/a"
        assert item["source"] == "Example"

    def test_nvd_basic(self):
        raw = {
            "id": "CVE-2026-1234",
            "descriptions": [{"lang": "en", "value": "A critical vulnerability."}],
            "published": "2026-01-01T00:00:00.000",
            "references": [{"url": "https://nvd.nist.gov/vuln/detail/CVE-2026-1234"}],
        }
        item = normalize_nvd(raw)
        assert item["title"] == "CVE-2026-1234"
        assert "critical" in item["description"].lower()

    def test_html_stripped(self):
        raw = {
            "title": "<b>Bold Title</b>",
            "description": "<p>HTML <em>content</em></p>",
            "publishedAt": "",
            "url": "https://x.com",
            "source": {"name": "X"},
        }
        item = normalize_newsapi(raw)
        assert "<" not in item["title"]
        assert "<" not in item["description"]

    def test_rss_basic(self):
        raw = {
            "title": "RSS Item",
            "summary": "Summary text",
            "link": "https://blog.example.com/post1",
            "published": "Thu, 01 Jan 2026 10:00:00 +0000",
            "_feed_name": "Test Feed",
        }
        item = normalize_rss(raw)
        assert item["title"] == "RSS Item"
        assert item["source"] == "Test Feed"


# ── Text generator tests ──────────────────────────────────────────────────────

from generators.text_generator import generate_template, _build_hashtags


class TestTextGenerator:
    def _item(self, **kw):
        return {
            "title": "CVE-2026-1234 critical RCE in Apache",
            "description": "A critical RCE was found in Apache 2.4.",
            "category": "vulnerability",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-1234",
            "source": "NVD",
            **kw,
        }

    def test_caption_contains_brand_hashtag(self):
        caption = generate_template(self._item())
        assert "#codeXploit" in caption

    def test_caption_contains_year_2026(self):
        caption = generate_template(self._item())
        assert "2026" in caption

    def test_caption_contains_cve(self):
        caption = generate_template(self._item())
        assert "CVE-2026-1234" in caption

    def test_caption_contains_url(self):
        caption = generate_template(self._item())
        assert "nvd.nist.gov" in caption

    def test_caption_contains_remediation(self):
        caption = generate_template(self._item())
        # Should have a patch/update/fix line
        lower = caption.lower()
        assert any(w in lower for w in ["patch", "update", "fix", "apply", "restrict"])

    def test_caption_length_in_range(self):
        caption = generate_template(self._item())
        words = len(caption.split())
        assert 40 <= words <= 300, f"Caption has {words} words"

    def test_fraud_caption(self):
        caption = generate_template(self._item(
            title="Massive phishing campaign targets Indian banks",
            category="fraud",
        ))
        assert "#codeXploit" in caption

    def test_hashtags_deduplicated(self):
        tags = _build_hashtags("vulnerability", "CVE-2026-1")
        seen = set()
        for t in tags.split():
            assert t.lower() not in seen, f"Duplicate hashtag: {t}"
            seen.add(t.lower())

    def test_hashtags_max_six(self):
        tags = _build_hashtags("news", "some title")
        assert len(tags.split()) <= 6

    def test_deterministic_output(self):
        """Same input → same output (no randomness in template mode)."""
        item = self._item()
        assert generate_template(item) == generate_template(item)


# ── Brand config tests ────────────────────────────────────────────────────────

from brand.brand_config import BRAND, load_from_html


class TestBrandConfig:
    def test_brand_has_required_keys(self):
        required = [
            "page_title", "person_name", "job_title", "brand_hashtag",
            "top_hashtags", "watermark_text", "same_as", "knows_about",
        ]
        for key in required:
            assert key in BRAND, f"Missing brand key: {key}"

    def test_brand_hashtag_format(self):
        assert BRAND["brand_hashtag"].startswith("#")

    def test_load_from_html(self, tmp_path):
        html = """<html><head>
        <title>Test Title</title>
        <meta name="description" content="Test description" />
        <meta name="keywords" content="security, hacking, python" />
        </head></html>"""
        p = tmp_path / "test.html"
        p.write_text(html)
        result = load_from_html(p)
        assert result["page_title"] == "Test Title"
        assert "security" in result["meta_keywords"]

    def test_load_from_missing_html_returns_defaults(self):
        result = load_from_html("/nonexistent/path.html")
        assert result["brand_name"] == BRAND["brand_name"]


# ── Storage organiser tests ───────────────────────────────────────────────────

from storage.organiser import item_dir, save_post, save_meta, save_review


class TestOrganiser:
    def _item(self):
        return {
            "title": "Test Security Alert",
            "description": "Test desc",
            "url": "https://example.com",
            "published_at": "2026-01-15T10:00:00Z",
            "source": "Test",
            "category": "vulnerability",
        }

    def test_item_dir_path_structure(self, tmp_path):
        d = item_dir(tmp_path, self._item(), "cve:CVE-2026-TEST")
        parts = d.relative_to(tmp_path).parts
        assert parts[0] == "vulnerability"
        assert parts[1] == "2026-01-15"
        assert d.exists()

    def test_slug_collision_avoided(self, tmp_path):
        """Two items with same title but different IDs get different dirs."""
        d1 = item_dir(tmp_path, self._item(), "cve:CVE-2026-001")
        d2 = item_dir(tmp_path, self._item(), "cve:CVE-2026-002")
        assert d1 != d2

    def test_save_post(self, tmp_path):
        d = item_dir(tmp_path, self._item(), "cve:CVE-2026-TEST-SAVE")
        path = save_post(d, "Test caption #codeXploit", self._item())
        assert path.exists()
        content = path.read_text()
        assert "Test caption" in content
        assert "codeXploit" in content

    def test_save_meta_json_valid(self, tmp_path):
        d = item_dir(tmp_path, self._item(), "cve:CVE-2026-TEST-META")
        path = save_meta(d, self._item(), "cve:CVE-2026-TEST-META")
        assert path.exists()
        meta = json.loads(path.read_text())
        assert meta["canonical_id"] == "cve:CVE-2026-TEST-META"
        assert meta["category"] == "vulnerability"

    def test_save_review(self, tmp_path):
        d = tmp_path / "flagged_item"
        d.mkdir()
        path = save_review(d, "MANUAL REVIEW REQUIRED\nReason: PoC detected")
        assert path.exists()
        assert "MANUAL REVIEW" in path.read_text()
