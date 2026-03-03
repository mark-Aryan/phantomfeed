"""
banner.py
=========
PhantomFeed — ASCII art banner with ANSI colour, version info,
and live stats. Displayed on every CLI invocation.

Inspired by the terminal aesthetics of Metasploit, Hydra, and Nmap.
"""

from __future__ import annotations

import datetime
import os
import platform
import sys
from pathlib import Path


# ── ANSI colour codes ──────────────────────────────────────────────────────────

class C:
    """Terminal colour constants. Auto-disabled on non-TTY / Windows without VT."""
    _on = (sys.stdout.isatty() and os.name != "nt") or (
        os.name == "nt" and os.environ.get("WT_SESSION")  # Windows Terminal
    )

    RST   = "\033[0m"    if _on else ""
    BOLD  = "\033[1m"    if _on else ""
    DIM   = "\033[2m"    if _on else ""

    # codeXploit brand palette
    CYAN  = "\033[96m"   if _on else ""   # primary accent  #00d4ff
    BLUE  = "\033[34m"   if _on else ""   # secondary       #004BCC
    LBLUE = "\033[94m"   if _on else ""   # light blue      #1a6ef7
    WHITE = "\033[97m"   if _on else ""
    GRAY  = "\033[90m"   if _on else ""
    RED   = "\033[91m"   if _on else ""
    GREEN = "\033[92m"   if _on else ""
    YELL  = "\033[93m"   if _on else ""
    MAG   = "\033[95m"   if _on else ""


# ── ASCII art  (hand-crafted, 58-char wide) ────────────────────────────────────
# Font style: "ANSI Shadow" variant, trimmed for 80-col terminals

_ART_PHANTOM = r"""
  ██████╗ ██╗  ██╗ █████╗ ███╗  ██╗████████╗ ██████╗ ███╗   ███╗
  ██╔══██╗██║  ██║██╔══██╗████╗ ██║╚══██╔══╝██╔═══██╗████╗ ████║
  ██████╔╝███████║███████║██╔██╗██║   ██║   ██║   ██║██╔████╔██║
  ██╔═══╝ ██╔══██║██╔══██║██║╚████║   ██║   ██║   ██║██║╚██╔╝██║
  ██║     ██║  ██║██║  ██║██║ ╚███║   ██║   ╚██████╔╝██║ ╚═╝ ██║
  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝"""

_ART_FEED = r"""
              ███████╗███████╗███████╗██████╗
              ██╔════╝██╔════╝██╔════╝██╔══██╗
              █████╗  █████╗  █████╗  ██║  ██║
              ██╔══╝  ██╔══╝  ██╔══╝  ██║  ██║
              ██║     ███████╗███████╗██████╔╝
              ╚═╝     ╚══════╝╚══════╝╚═════╝"""


# ── Decorative divider lines ──────────────────────────────────────────────────

def _div(char: str = "─", width: int = 72) -> str:
    return C.GRAY + char * width + C.RST


def _box_line(text: str, width: int = 70, pad: int = 2) -> str:
    """  ║  text                                      ║  """
    inner = width - 2 * pad
    content = text.ljust(inner)[:inner]
    return f"  {C.GRAY}║{C.RST}{' ' * pad}{content}{' ' * pad}{C.GRAY}║{C.RST}"


def _box_top(width: int = 70) -> str:
    return f"  {C.GRAY}╔{'═' * (width - 2)}╗{C.RST}"


def _box_bot(width: int = 70) -> str:
    return f"  {C.GRAY}╚{'═' * (width - 2)}╝{C.RST}"


def _box_mid(width: int = 70) -> str:
    return f"  {C.GRAY}╠{'═' * (width - 2)}╣{C.RST}"


# ── Stats loader ──────────────────────────────────────────────────────────────

def _load_stats(db_path: str = "data/dedupe.db") -> dict:
    """Read live stats from SQLite without importing the full pipeline."""
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT COUNT(*) t, SUM(flagged) f,"
            " SUM(CASE WHEN category='vulnerability' THEN 1 ELSE 0 END) v,"
            " SUM(CASE WHEN category='incident' THEN 1 ELSE 0 END) i,"
            " SUM(CASE WHEN category='fraud' THEN 1 ELSE 0 END) fr,"
            " SUM(CASE WHEN category='news' THEN 1 ELSE 0 END) n"
            " FROM processed"
        ).fetchone()
        conn.close()
        if row and row[0]:
            return {
                "total": row[0] or 0,
                "flagged": row[1] or 0,
                "vulnerability": row[2] or 0,
                "incident": row[3] or 0,
                "fraud": row[4] or 0,
                "news": row[5] or 0,
            }
    except Exception:
        pass
    return {}


def _read_status_file(path: str = "status.json") -> dict:
    try:
        return __import__("json").loads(Path(path).read_text())
    except Exception:
        return {}


# ── Version / meta ────────────────────────────────────────────────────────────

VERSION     = "1.0.0"
CODENAME    = "wraith"
AUTHOR      = "Aryan Kumar Upadhyay"
BRAND       = "codeXploit"
WEBSITE     = "codexploit.in"
TWITTER     = "@aryankrupadhyay"
GITHUB      = "github.com/mark-Aryan"
SOURCES     = 3          # NewsAPI + NVD + RSS
RSS_FEEDS   = 6
CATEGORIES  = 5
SAFETY_RULES= 18


# ── Main banner function ──────────────────────────────────────────────────────

def print_banner(
    db_path:     str = "data/dedupe.db",
    status_file: str = "status.json",
    command:     str = "",
) -> None:
    """
    Print the full PhantomFeed banner to stdout.
    Call this at the start of every CLI command.
    """
    stats   = _load_stats(db_path)
    metrics = _read_status_file(status_file)
    now     = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    py_ver  = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    os_name = platform.system()

    W = 70  # box inner width

    lines: list[str] = [""]

    # ── ASCII art ─────────────────────────────────────────────────────────────
    for ln in _ART_PHANTOM.split("\n"):
        lines.append(C.CYAN + C.BOLD + ln + C.RST)
    for ln in _ART_FEED.split("\n"):
        lines.append(C.LBLUE + C.BOLD + ln + C.RST)

    lines.append("")

    # ── Tagline ───────────────────────────────────────────────────────────────
    tag  = "Ghost in the machine.  Signal in the noise."
    pad  = (W - len(tag)) // 2 + 2
    lines.append(" " * pad + C.GRAY + C.BOLD + tag + C.RST)
    lines.append("")
    lines.append(_div("─", 72))
    lines.append("")

    # ── Info box (left column / right column layout) ──────────────────────────
    lines.append(_box_top(W))

    # Row 1: version | date
    lhs = f"{C.GRAY}Version   {C.RST}{C.CYAN}{VERSION}{C.RST}  {C.GRAY}({CODENAME}){C.RST}"
    rhs = f"{C.GRAY}Date      {C.RST}{C.WHITE}{now}{C.RST}"
    lines.append(_fmt_two_col(lhs, rhs, W))

    # Row 2: author | python
    lhs = f"{C.GRAY}Author    {C.RST}{C.WHITE}{AUTHOR}{C.RST}"
    rhs = f"{C.GRAY}Python    {C.RST}{C.WHITE}{py_ver}{C.RST}  /  {C.WHITE}{os_name}{C.RST}"
    lines.append(_fmt_two_col(lhs, rhs, W))

    # Row 3: brand | website
    lhs = f"{C.GRAY}Brand     {C.RST}{C.CYAN}{BRAND}{C.RST}"
    rhs = f"{C.GRAY}Web       {C.RST}{C.CYAN}{WEBSITE}{C.RST}"
    lines.append(_fmt_two_col(lhs, rhs, W))

    # Row 4: twitter | github
    lhs = f"{C.GRAY}Twitter   {C.RST}{C.LBLUE}{TWITTER}{C.RST}"
    rhs = f"{C.GRAY}GitHub    {C.RST}{C.LBLUE}{GITHUB}{C.RST}"
    lines.append(_fmt_two_col(lhs, rhs, W))

    lines.append(_box_mid(W))

    # ── Feed / engine stats ───────────────────────────────────────────────────
    lhs = (f"{C.GRAY}Sources   {C.RST}{C.GREEN}{SOURCES}{C.RST}"
           f"  {C.GRAY}(NewsAPI + NVD/CVE + RSS){C.RST}")
    rhs = (f"{C.GRAY}RSS feeds {C.RST}{C.GREEN}{RSS_FEEDS}{C.RST}")
    lines.append(_fmt_two_col(lhs, rhs, W))

    lhs = (f"{C.GRAY}Categories{C.RST}{C.GREEN} {CATEGORIES}{C.RST}"
           f"  {C.GRAY}(vuln/incident/fraud/bug/news){C.RST}")
    rhs = (f"{C.GRAY}Safety rules  {C.RST}{C.GREEN}{SAFETY_RULES}{C.RST}")
    lines.append(_fmt_two_col(lhs, rhs, W))

    lines.append(_box_mid(W))

    # ── Live DB stats (if available) ──────────────────────────────────────────
    if stats:
        total   = stats.get("total", 0)
        flagged = stats.get("flagged", 0)
        vulns   = stats.get("vulnerability", 0)
        inc     = stats.get("incident", 0)
        fraud   = stats.get("fraud", 0)
        news_n  = stats.get("news", 0)

        lhs = (f"{C.GRAY}Processed {C.RST}{C.YELL}{total}{C.RST}"
               f"  {C.GRAY}items total  │  {C.RST}"
               f"{C.RED}⚑ {flagged} flagged{C.RST}")
        rhs = ""
        lines.append(_fmt_two_col(lhs, rhs, W))

        lhs = (f"  {C.RED}⬤{C.RST} vuln {C.CYAN}{vulns:<5}{C.RST}"
               f"  {C.YELL}⬤{C.RST} incident {C.CYAN}{inc:<5}{C.RST}"
               f"  {C.MAG}⬤{C.RST} fraud {C.CYAN}{fraud:<5}{C.RST}"
               f"  {C.BLUE}⬤{C.RST} news {C.CYAN}{news_n}{C.RST}")
        lines.append(_fmt_two_col(lhs, "", W))

        if metrics:
            gen  = metrics.get("generated", 0)
            skip = metrics.get("skipped_dupe", 0) + metrics.get("skipped_similar", 0)
            lhs  = (f"{C.GRAY}Generated {C.RST}{C.GREEN}{gen}{C.RST}"
                    f"  {C.GRAY}│  Skipped {C.RST}{C.GRAY}{skip}{C.RST}"
                    f"  {C.GRAY}│  Last run {C.RST}{C.WHITE}"
                    f"{metrics.get('updated_at','—')[:19]}{C.RST}")
            lines.append(_fmt_two_col(lhs, "", W))
    else:
        lines.append(_box_line(
            f"  {C.GRAY}No data yet — run:{C.RST}  "
            f"{C.CYAN}python cli.py seed{C.RST}  "
            f"{C.GRAY}to populate{C.RST}",
            W,
        ))

    lines.append(_box_bot(W))
    lines.append("")

    # ── Active command highlight ───────────────────────────────────────────────
    if command:
        cmd_map = {
            "daemon":      (C.GREEN,  "▶  DAEMON MODE  —  running 24×7 poll loop"),
            "start":       (C.CYAN,   "▶  SINGLE CYCLE  —  fetch → process → save"),
            "seed":        (C.YELL,   "▶  SEED MODE  —  injecting test items"),
            "status":      (C.LBLUE,  "▶  STATUS  —  reading DB & metrics"),
            "reprocess":   (C.YELL,   "▶  REPROCESS  —  force-reprocessing item"),
            "purge":       (C.RED,    "▶  PURGE  —  deleting all DB records"),
            "healthcheck": (C.GREEN,  "▶  HEALTHCHECK  —  starting HTTP server"),
        }
        colour, label = cmd_map.get(command, (C.WHITE, f"▶  {command.upper()}"))
        lines.append(
            f"  {colour}{C.BOLD}  {label}  {C.RST}"
        )
        lines.append("")

    # ── Flush ─────────────────────────────────────────────────────────────────
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def _fmt_two_col(lhs: str, rhs: str, box_w: int = 70) -> str:
    """
    Render two coloured strings side-by-side inside a box row.
    Strips ANSI codes only for width accounting.
    """
    import re
    _strip = lambda s: re.sub(r"\033\[[0-9;]*m", "", s)

    lhs_plain = _strip(lhs)
    rhs_plain = _strip(rhs)
    total_plain = len(lhs_plain) + len(rhs_plain)
    gap = max(1, box_w - total_plain - 4)  # 4 = 2×border + 2×inner-pad

    return f"  {C.GRAY}║{C.RST}  {lhs}{' ' * gap}{rhs}  {C.GRAY}║{C.RST}"


# ── Minimal "already printed" guard ───────────────────────────────────────────
_banner_shown = False

def show(command: str = "", db_path: str = "data/dedupe.db",
         status_file: str = "status.json", force: bool = False) -> None:
    """Show banner once per process unless force=True."""
    global _banner_shown
    if _banner_shown and not force:
        return
    _banner_shown = True
    print_banner(db_path=db_path, status_file=status_file, command=command)


# ── Standalone preview ────────────────────────────────────────────────────────
if __name__ == "__main__":
    show(command="daemon", force=True)
