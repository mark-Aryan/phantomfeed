"""
publisher/git_autopush.py  ★ FIXED ★
======================================
ROOT CAUSE FIX for uploading 419 files every single cycle:

The original _git_push_api() did a separate GET /contents/{path} request
for EVERY file to check its current SHA before uploading.
With 419 files: 419 GET requests + 419 PUT requests = 838 API calls per cycle.
At 0.1s sleep between each = ~84 seconds per push, hitting GitHub secondary 
rate limits and causing the daemon to stop.

FIX: Use GitHub's Git Trees API (/repos/{repo}/git/trees/{sha}?recursive=1)
to fetch ALL file SHAs in ONE request, then compare locally.
Only upload files that are NEW or CHANGED.
Typical result: 2-3 files changed per cycle vs 419 → 50x faster.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ─── Mode A: Local Git ────────────────────────────────────────────────────────

def _git_push_local(
    blog_dir: str | Path,
    out_dir:  str | Path,
    message:  str,
    branch:   str = "gh-pages",
) -> bool:
    blog_dir = Path(blog_dir)
    out_dir  = Path(out_dir)

    def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
        result = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None,
            capture_output=True, text=True
        )
        return result.returncode, (result.stdout + result.stderr).strip()

    # Find repo root
    repo_root = Path.cwd()
    code, out = _run(["git", "rev-parse", "--show-toplevel"])
    if code == 0 and out:
        repo_root = Path(out.strip())

    log.info("[AutoPush-Git] Repo root: %s", repo_root)

    # Set identity (needed on fresh servers / CI)
    _run(["git", "config", "--global", "user.email", "bot@codexploit.in"])
    _run(["git", "config", "--global", "user.name",  "PhantomFeed Bot"])

    # Ensure .nojekyll exists so GitHub Pages works
    nojekyll = blog_dir / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.write_text("", encoding="utf-8")

    # Stage files
    for folder in [str(blog_dir), str(out_dir)]:
        code, out = _run(["git", "add", folder], cwd=repo_root)
        if code != 0:
            log.warning("[AutoPush-Git] git add failed for %s: %s", folder, out)

    # Check for changes
    code, status = _run(["git", "status", "--porcelain"], cwd=repo_root)
    if not status.strip():
        log.info("[AutoPush-Git] Nothing changed — skipping push.")
        return True

    # Commit
    code, out = _run(["git", "commit", "-m", message], cwd=repo_root)
    if code != 0:
        log.error("[AutoPush-Git] git commit failed: %s", out)
        return False
    log.info("[AutoPush-Git] Committed: %s", out[:80])

    # Push
    code, out = _run(["git", "push", "origin", branch], cwd=repo_root)
    if code != 0:
        log.error("[AutoPush-Git] git push failed: %s", out)
        return False

    log.info("[AutoPush-Git] ✅ Pushed to origin/%s", branch)
    return True


# ─── Mode B: GitHub REST API (FIXED) ─────────────────────────────────────────

def _api_request(
    method: str,
    path:   str,
    token:  str,
    body:   dict | None = None,
) -> dict:
    url  = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization":        f"Bearer {token}",
            "Accept":               "application/vnd.github+json",
            "Content-Type":         "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent":           "PhantomFeed/2.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} → {e.code}: {body_text}") from e


def _git_blob_sha(content: bytes) -> str:
    """
    Compute the SHA that GitHub uses for blob objects.
    Formula: sha1("blob {len}\0{content}")
    This lets us compare local vs remote WITHOUT an API call per file.
    """
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()


def _get_all_remote_shas(token: str, repo: str, branch: str) -> dict[str, str]:
    """
    FIX: Returns {filepath: blob_sha} for every file on the branch.
    Uses ONE API call (Git Trees recursive) instead of N calls.
    """
    try:
        # Step 1: get branch HEAD SHA
        ref = _api_request("GET", f"/repos/{repo}/git/ref/heads/{branch}", token)
        commit_sha = ref["object"]["sha"]
        # Step 2: get full recursive tree in one request
        tree = _api_request(
            "GET",
            f"/repos/{repo}/git/trees/{commit_sha}?recursive=1",
            token,
        )
        return {
            item["path"]: item["sha"]
            for item in tree.get("tree", [])
            if item.get("type") == "blob"
        }
    except Exception as exc:
        log.warning("[AutoPush-API] Could not fetch remote tree: %s — will upload all", exc)
        return {}


def _ensure_branch_exists(token: str, repo: str, branch: str) -> None:
    try:
        _api_request("GET", f"/repos/{repo}/branches/{branch}", token)
        return  # already exists
    except Exception:
        pass
    for default in ("main", "master"):
        try:
            ref = _api_request("GET", f"/repos/{repo}/git/ref/heads/{default}", token)
            _api_request("POST", f"/repos/{repo}/git/refs", token, {
                "ref": f"refs/heads/{branch}",
                "sha": ref["object"]["sha"],
            })
            log.info("[AutoPush-API] Created branch: %s", branch)
            return
        except Exception:
            continue
    log.warning("[AutoPush-API] Could not create branch %s", branch)


def _upsert_file(
    token:       str,
    repo:        str,
    path:        str,
    content:     bytes,
    message:     str,
    branch:      str,
    remote_sha:  str | None = None,
) -> None:
    """Upload or update a single file. remote_sha required for updates."""
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content).decode(),
        "branch":  branch,
    }
    if remote_sha:
        body["sha"] = remote_sha
    _api_request("PUT", f"/repos/{repo}/contents/{path}", token, body)


def _git_push_api(
    blog_dir: str | Path,
    token:    str,
    repo:     str,
    branch:   str,
    message:  str,
) -> bool:
    blog_dir = Path(blog_dir)
    if not blog_dir.exists():
        log.error("[AutoPush-API] blog_dir does not exist: %s", blog_dir)
        return False

    _ensure_branch_exists(token, repo, branch)

    # FIX: Fetch ALL remote SHAs in ONE request
    remote_shas = _get_all_remote_shas(token, repo, branch)
    log.info("[AutoPush-API] Remote has %d tracked files", len(remote_shas))

    # Collect local files and compute which ones changed
    all_local = [f for f in blog_dir.rglob("*") if f.is_file()]
    to_upload: list[tuple[str, bytes, str | None]] = []

    for fpath in all_local:
        rel_path = fpath.relative_to(blog_dir).as_posix()
        content  = fpath.read_bytes()
        local_sha = _git_blob_sha(content)
        remote_sha = remote_shas.get(rel_path)

        if remote_sha == local_sha:
            continue  # unchanged — skip

        to_upload.append((rel_path, content, remote_sha))

    # Always ensure .nojekyll exists
    if ".nojekyll" not in remote_shas:
        to_upload.append((".nojekyll", b"", None))

    if not to_upload:
        log.info("[AutoPush-API] All %d files unchanged — skipping push", len(all_local))
        return True

    log.info(
        "[AutoPush-API] Uploading %d changed files (of %d total) to %s@%s",
        len(to_upload), len(all_local), repo, branch,
    )

    success = fail = 0
    for rel_path, content, remote_sha in to_upload:
        try:
            _upsert_file(token, repo, rel_path, content, message, branch, remote_sha)
            log.debug("[AutoPush-API] ✓ %s", rel_path)
            success += 1
            time.sleep(0.05)  # brief pause — much less needed since far fewer uploads
        except Exception as exc:
            log.warning("[AutoPush-API] ✗ Failed %s: %s", rel_path, exc)
            fail += 1

    log.info(
        "[AutoPush-API] ✅ Done: %d uploaded, %d failed → %s@%s",
        success, fail, repo, branch,
    )
    return fail == 0


# ─── Public entry point ────────────────────────────────────────────────────────

def autopush(
    config:     dict[str, Any],
    blog_dir:   str | Path = "blog",
    out_dir:    str | Path = "out",
    post_count: int = 0,
) -> bool:
    """
    Auto-push blog to GitHub after every daemon cycle.
    Called by core_v2.py — returns True on success (non-fatal on failure).
    """
    if not config.get("autopush_enabled", False):
        return True   # disabled — silent no-op

    token  = config.get("github_token")  or os.getenv("GITHUB_TOKEN",  "")
    repo   = config.get("github_repo")   or os.getenv("GITHUB_REPO",   "")
    branch = config.get("github_branch", "gh-pages")
    mode   = config.get("autopush_mode", "api")

    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = config.get(
        "autopush_message",
        "🤖 PhantomFeed auto-update — {timestamp} ({n} posts)",
    ).format(timestamp=ts, n=post_count)

    log.info("[AutoPush] mode=%s  repo=%s  branch=%s", mode, repo or "(local)", branch)

    try:
        if mode == "api":
            if not token:
                log.error("[AutoPush] GITHUB_TOKEN not set — cannot push")
                return False
            if not repo:
                log.error("[AutoPush] GITHUB_REPO not set — cannot push")
                return False
            return _git_push_api(blog_dir, token, repo, branch, msg)
        else:
            if token and repo:
                _inject_token_into_remote(token, repo)
            return _git_push_local(blog_dir, out_dir, msg, branch)
    except Exception as exc:
        log.error("[AutoPush] Push failed (non-fatal): %s", exc)
        return False


def _inject_token_into_remote(token: str, repo: str) -> None:
    """Inject PAT into remote URL so `git push` doesn't ask for password."""
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    try:
        subprocess.run(
            ["git", "remote", "set-url", "origin", url],
            capture_output=True, check=False,
        )
    except Exception:
        pass
