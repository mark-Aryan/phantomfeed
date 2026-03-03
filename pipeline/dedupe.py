"""
pipeline/dedupe.py
==================
Deterministic deduplication with SQLite persistence.

Canonical ID rules (in priority order):
  1. CVE-ID found in title/url  → "cve:<CVE-YYYY-NNNNN>"
  2. URL present                → "url:<sha256[:16]>"
  3. Fallback                   → "hash:<sha256[:16]>" of
     (title_normalised + publishedAt_to_minute + source)

The DB stores processed IDs so re-starts never re-process items.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Helpers ────────────────────────────────────────────────────────────────────

_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)


def _norm_title(title: str) -> str:
    """Lower-case, strip accents, collapse whitespace."""
    t = unicodedata.normalize("NFKD", title)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def _trunc_to_minute(dt_str: str) -> str:
    """Return ISO timestamp truncated to the minute, or raw string on failure."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%MZ",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
    ):
        try:
            dt = datetime.strptime(dt_str, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            continue
    return dt_str[:16]  # best-effort slice


def canonical_id(
    *,
    title: str = "",
    url: str = "",
    published_at: str = "",
    source: str = "",
) -> str:
    """Return a deterministic canonical ID string for a feed item."""
    # 1. CVE ID anywhere in title or url
    cve_match = _CVE_RE.search(title) or _CVE_RE.search(url)
    if cve_match:
        return "cve:" + cve_match.group(0).upper()

    # 2. URL hash
    clean_url = url.strip().rstrip("/")
    if clean_url:
        h = hashlib.sha256(clean_url.encode()).hexdigest()[:16]
        return f"url:{h}"

    # 3. Fallback: title + time + source
    payload = "\n".join([
        _norm_title(title),
        _trunc_to_minute(published_at) if published_at else "",
        source.strip().lower(),
    ])
    h = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"hash:{h}"


def similarity(a: str, b: str) -> float:
    """Simple Jaccard token similarity of two normalised title strings."""
    ta = set(_norm_title(a).split())
    tb = set(_norm_title(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def slugify(text: str, max_len: int = 48) -> str:
    """Convert text to a URL-safe slug."""
    slug = _norm_title(text)
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:max_len]


# ── SQLite Store ───────────────────────────────────────────────────────────────

class DedupeDB:
    """Thread-safe SQLite store for processed item IDs."""

    DDL = """
    CREATE TABLE IF NOT EXISTS processed (
        canonical_id TEXT PRIMARY KEY,
        slug         TEXT NOT NULL,
        category     TEXT DEFAULT 'news',
        source       TEXT,
        url          TEXT,
        title        TEXT,
        published_at TEXT,
        processed_at TEXT NOT NULL,
        flagged      INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_slug   ON processed(slug);
    CREATE INDEX IF NOT EXISTS idx_source ON processed(source);
    """

    def __init__(self, db_path: str | Path = "data/dedupe.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self.DDL)
        self._conn.commit()

    # ── public API ──────────────────────────────────────────────────────────

    def is_processed(self, cid: str) -> bool:
        """Return True if canonical_id already in DB."""
        row = self._conn.execute(
            "SELECT 1 FROM processed WHERE canonical_id = ?", (cid,)
        ).fetchone()
        return row is not None

    def mark_processed(
        self,
        *,
        canonical_id: str,
        slug: str,
        category: str = "news",
        source: str = "",
        url: str = "",
        title: str = "",
        published_at: str = "",
        flagged: bool = False,
    ) -> None:
        """Insert a record; silently ignore duplicate key."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR IGNORE INTO processed
              (canonical_id, slug, category, source, url, title, published_at,
               processed_at, flagged)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (canonical_id, slug, category, source, url, title, published_at,
             now, int(flagged)),
        )
        self._conn.commit()

    def get(self, cid: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM processed WHERE canonical_id = ?", (cid,)
        ).fetchone()

    def delete(self, cid: str) -> bool:
        """Force-delete a record so it can be reprocessed."""
        c = self._conn.execute(
            "DELETE FROM processed WHERE canonical_id = ?", (cid,)
        )
        self._conn.commit()
        return c.rowcount > 0

    def purge(self) -> int:
        """Delete all records. Returns count removed."""
        c = self._conn.execute("DELETE FROM processed")
        self._conn.commit()
        return c.rowcount

    def stats(self) -> dict[str, int]:
        rows = self._conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(flagged) as flagged,
                SUM(CASE WHEN category='vulnerability' THEN 1 ELSE 0 END) as vulnerability,
                SUM(CASE WHEN category='fraud' THEN 1 ELSE 0 END) as fraud,
                SUM(CASE WHEN category='incident' THEN 1 ELSE 0 END) as incident,
                SUM(CASE WHEN category='bug' THEN 1 ELSE 0 END) as bug,
                SUM(CASE WHEN category='news' THEN 1 ELSE 0 END) as news
            FROM processed
            """
        ).fetchone()
        return dict(rows) if rows else {}

    def find_similar(self, title: str, threshold: float = 0.92) -> Optional[str]:
        """Return canonical_id of a record with similarity > threshold, or None."""
        rows = self._conn.execute(
            "SELECT canonical_id, title FROM processed WHERE title != ''"
        ).fetchall()
        for row in rows:
            if similarity(title, row["title"]) > threshold:
                return row["canonical_id"]
        return None

    def close(self) -> None:
        self._conn.close()
