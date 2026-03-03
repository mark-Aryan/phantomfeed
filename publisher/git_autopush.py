"""
publisher/git_autopush.py
==========================
Auto-pushes the blog/ folder to GitHub after every daemon cycle.

Works in two modes:
  (A) LOCAL GIT — runs `git add / commit / push` via subprocess
      (requires git installed + repo already configured with remote)

  (B) GITHUB API — pushes files directly via GitHub REST API
      (no git install needed, works on any server/VPS/cloud)
      Requires: GITHUB_TOKEN, GITHUB_REPO env vars

Config keys (config.json):
  autopush_enabled:  true
  autopush_mode:     "git"  | "api"
  github_token:      ""     (or set GITHUB_TOKEN env var)
  github_repo:       ""     (e.g. "mark-Aryan/phantomfeed" — set GITHUB_REPO env var)
  github_branch:     "gh-pages"
  autopush_message:  "🤖 PhantomFeed auto-update — {timestamp} ({n} posts)"
"""

from __future__ import annotations

import base64
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
    branch:   str = "main",
) -> bool:
    """
    Stage blog/ and out/ then commit + push using local git.
    Returns True on success.
    """
    blog_dir = Path(blog_dir)
    out_dir  = Path(out_dir)

    def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
        result = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None,
            capture_output=True, text=True
        )
        return result.returncode, (result.stdout + result.stderr).strip()

    # Find repo root (walk up from blog_dir)
    repo_root = Path.cwd()
    code, out = _run(["git", "rev-parse", "--show-toplevel"])
    if code == 0 and out:
        repo_root = Path(out.strip())

    log.info("[AutoPush-Git] Repo root: %s", repo_root)

    # Configure git identity if not set (needed on fresh servers)
    _run(["git", "config", "--global", "user.email", "bot@codexploit.in"])
    _run(["git", "config", "--global", "user.name",  "PhantomFeed Bot"])

    # Stage blog/ and out/
    for folder in [str(blog_dir), str(out_dir)]:
        code, out = _run(["git", "add", folder], cwd=repo_root)
        if code != 0:
            log.warning("[AutoPush-Git] git add failed for %s: %s", folder, out)

    # Check if anything changed
    code, status = _run(["git", "status", "--porcelain"], cwd=repo_root)
    if not status.strip():
        log.info("[AutoPush-Git] Nothing changed, skipping push.")
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


# ─── Mode B: GitHub REST API ──────────────────────────────────────────────────

def _api_request(
    method: str,
    path: str,
    token: str,
    body: dict | None = None,
) -> dict:
    """Make a GitHub API request. Returns parsed JSON response."""
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
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


def _get_file_sha(token: str, repo: str, path: str, branch: str) -> str | None:
    """Get the SHA of an existing file (needed for updates)."""
    try:
        data = _api_request(
            "GET", f"/repos/{repo}/contents/{path}?ref={branch}", token
        )
        return data.get("sha")
    except Exception:
        return None


def _upsert_file(
    token:   str,
    repo:    str,
    path:    str,
    content: bytes,
    message: str,
    branch:  str,
) -> None:
    """Create or update a single file via GitHub API."""
    sha = _get_file_sha(token, repo, path, branch)
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content).decode(),
        "branch":  branch,
    }
    if sha:
        body["sha"] = sha

    _api_request("PUT", f"/repos/{repo}/contents/{path}", token, body)


def _ensure_branch_exists(token: str, repo: str, branch: str) -> None:
    """Create branch from main if it doesn't exist yet."""
    try:
        _api_request("GET", f"/repos/{repo}/branches/{branch}", token)
        return   # branch exists
    except Exception:
        pass

    # Get SHA of default branch HEAD
    try:
        ref_data = _api_request("GET", f"/repos/{repo}/git/ref/heads/main", token)
        sha = ref_data["object"]["sha"]
    except Exception:
        try:
            ref_data = _api_request("GET", f"/repos/{repo}/git/ref/heads/master", token)
            sha = ref_data["object"]["sha"]
        except Exception:
            log.warning("[AutoPush-API] Could not find default branch to fork from")
            return

    try:
        _api_request("POST", f"/repos/{repo}/git/refs", token, {
            "ref": f"refs/heads/{branch}",
            "sha": sha,
        })
        log.info("[AutoPush-API] Created branch: %s", branch)
    except Exception as exc:
        log.warning("[AutoPush-API] Could not create branch %s: %s", branch, exc)


def _git_push_api(
    blog_dir: str | Path,
    token:    str,
    repo:     str,
    branch:   str,
    message:  str,
) -> bool:
    """
    Push all files in blog_dir to GitHub via REST API.
    This is the recommended mode for servers without git.
    """
    blog_dir = Path(blog_dir)
    if not blog_dir.exists():
        log.error("[AutoPush-API] blog_dir does not exist: %s", blog_dir)
        return False

    _ensure_branch_exists(token, repo, branch)

    # Collect all files
    all_files = [f for f in blog_dir.rglob("*") if f.is_file()]
    log.info("[AutoPush-API] Uploading %d files to %s@%s", len(all_files), repo, branch)

    success_count = 0
    fail_count    = 0

    for fpath in all_files:
        rel = fpath.relative_to(blog_dir).as_posix()
        try:
            content = fpath.read_bytes()
            _upsert_file(token, repo, rel, content, message, branch)
            success_count += 1
            # Respect GitHub API rate limit (5000 req/hr authenticated)
            time.sleep(0.1)
        except Exception as exc:
            log.warning("[AutoPush-API] Failed to upload %s: %s", rel, exc)
            fail_count += 1

    # Add .nojekyll so GitHub Pages doesn't try to process as Jekyll
    try:
        _upsert_file(token, repo, ".nojekyll", b"", message, branch)
    except Exception:
        pass

    log.info(
        "[AutoPush-API] Done: %d uploaded, %d failed → %s@%s",
        success_count, fail_count, repo, branch,
    )
    return fail_count == 0


# ─── Public entry point ────────────────────────────────────────────────────────

def autopush(
    config:    dict[str, Any],
    blog_dir:  str | Path = "blog",
    out_dir:   str | Path = "out",
    post_count: int = 0,
) -> bool:
    """
    Auto-push blog to GitHub.
    Called automatically by core_v2.py after every successful cycle.

    Returns True on success, False on failure (non-fatal).
    """
    if not config.get("autopush_enabled", False):
        return True   # disabled — silent no-op

    token  = config.get("github_token")  or os.getenv("GITHUB_TOKEN",  "")
    repo   = config.get("github_repo")   or os.getenv("GITHUB_REPO",   "")
    branch = config.get("github_branch", "gh-pages")
    mode   = config.get("autopush_mode", "git")

    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = config.get(
        "autopush_message",
        "🤖 PhantomFeed auto-update — {timestamp} ({n} posts)"
    ).format(timestamp=ts, n=post_count)

    log.info("[AutoPush] mode=%s  repo=%s  branch=%s", mode, repo or "(local)", branch)

    try:
        if mode == "api":
            if not token:
                log.error("[AutoPush] GITHUB_TOKEN not set — cannot use API mode")
                return False
            if not repo:
                log.error("[AutoPush] GITHUB_REPO not set — cannot use API mode")
                return False
            return _git_push_api(blog_dir, token, repo, branch, msg)
        else:
            # git mode — token injected into remote URL if provided
            if token and repo:
                _inject_token_into_remote(token, repo)
            return _git_push_local(blog_dir, out_dir, msg, branch)
    except Exception as exc:
        log.error("[AutoPush] Push failed (non-fatal): %s", exc)
        return False


def _inject_token_into_remote(token: str, repo: str) -> None:
    """Set remote URL with token so push doesn't ask for password."""
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    try:
        subprocess.run(
            ["git", "remote", "set-url", "origin", url],
            capture_output=True, check=False
        )
    except Exception:
        pass
