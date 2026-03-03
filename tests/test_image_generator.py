"""
tests/test_image_generator.py
==============================
Tests for image generation (placeholder backend only — no API key needed).
"""

from __future__ import annotations

from pathlib import Path

import pytest


SAMPLE_ITEM = {
    "title": "CVE-2026-1234 critical RCE in Apache HTTP Server",
    "description": "A critical remote code execution vulnerability.",
    "category": "vulnerability",
    "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-1234",
    "source": "NVD",
    "published_at": "2026-01-15T10:00:00Z",
}


class TestImageGenerator:
    def test_placeholder_creates_files(self, tmp_path):
        from generators.image_generator import generate_placeholder

        raw_path, final_path = generate_placeholder(SAMPLE_ITEM, tmp_path)
        assert raw_path.exists(), "image_raw.png was not created"
        assert final_path.exists(), "image.png was not created"

    def test_placeholder_file_sizes_nonzero(self, tmp_path):
        from generators.image_generator import generate_placeholder

        raw_path, final_path = generate_placeholder(SAMPLE_ITEM, tmp_path)
        assert raw_path.stat().st_size > 1000
        assert final_path.stat().st_size > 1000

    def test_placeholder_linkedin_dimensions(self, tmp_path):
        from generators.image_generator import generate_placeholder, LINKEDIN_W, LINKEDIN_H
        from PIL import Image

        _, final_path = generate_placeholder(SAMPLE_ITEM, tmp_path)
        with Image.open(final_path) as img:
            assert img.size == (LINKEDIN_W, LINKEDIN_H)

    def test_placeholder_square_dimensions(self, tmp_path):
        from generators.image_generator import generate_placeholder, SQUARE_W, SQUARE_H
        from PIL import Image

        _, final_path = generate_placeholder(SAMPLE_ITEM, tmp_path, size=(SQUARE_W, SQUARE_H))
        with Image.open(final_path) as img:
            assert img.size == (SQUARE_W, SQUARE_H)

    def test_generate_dispatch_placeholder(self, tmp_path):
        from generators.image_generator import generate

        raw_path, final_path = generate(
            SAMPLE_ITEM, tmp_path, config={"image_backend": "placeholder"}
        )
        assert raw_path.exists()
        assert final_path.exists()

    def test_all_categories_generate(self, tmp_path):
        from generators.image_generator import generate_placeholder

        for cat in ["vulnerability", "fraud", "bug", "incident", "news"]:
            item = {**SAMPLE_ITEM, "category": cat}
            d = tmp_path / cat
            d.mkdir(parents=True, exist_ok=True)
            raw_path, final_path = generate_placeholder(item, d)
            assert final_path.exists(), f"Image not created for category: {cat}"
