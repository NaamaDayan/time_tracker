"""
Context reader.

Reads the "Daily Plans - Plan VS Actual" Notion page (config["notion_context_page_id"]).

Structure:
  [context page]
    ├── child_page "General Context"   ← static background; read by load_general_context()
    └── child_page "YYYY-MM-DD"        ← one per day; read by load_daily_entry(date)
           ## Plan
           ...
           ## Actual
           ...
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import sys
from functools import lru_cache

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from config_loader import get_config
from utils.logger import get_logger
from utils.notion_client import get_notion

log = get_logger("fetch_context")

_HEADING_TYPES = {"heading_1", "heading_2", "heading_3"}
GENERAL_CONTEXT_TITLE = "General Context"


# ── Block utilities ──────────────────────────────────────────────────────────

def _plain_text(block: dict) -> str:
    btype = block.get("type", "")
    return "".join(
        s.get("plain_text", "")
        for s in block.get(btype, {}).get("rich_text", [])
    )


_ACCESS_HINT = (
    "Notion 404 — the integration lacks access to the context page.\n"
    "Fix: open 'Daily Plans - Plan VS Actual' in Notion → ··· → Connections\n"
    "→ add your integration, then retry."
)


def _fetch_all_blocks(block_id: str) -> list[dict]:
    notion = get_notion()
    results: list[dict] = []
    cursor: str | None = None
    while True:
        kwargs: dict = {"block_id": block_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.blocks.children.list(**kwargs)
        results.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results


def _blocks_to_plaintext(blocks: list[dict], max_chars: int | None = None) -> str:
    """
    Convert a list of blocks to a plain-text string.

    Mapping:
      heading_1/2/3       → "## {text}\n"
      paragraph           → "{text}\n"
      bulleted_list_item  → "• {text}\n"
      numbered_list_item  → "{n}. {text}\n"
      divider             → "---\n"
      to_do               → "- [x] / - [ ] {text}\n"
      child_page          → "[sub-page: {title}]\n"
      toggle              → "{toggle summary}\n"   (children skipped)
      other               → "{text}\n"

    Truncates at max_chars at a paragraph boundary if provided.
    """
    lines: list[str] = []
    total_chars = 0
    n_counter = 0

    for block in blocks:
        btype = block.get("type", "")

        if btype in _HEADING_TYPES:
            n_counter = 0
            line = f"## {_plain_text(block)}\n"
        elif btype == "bulleted_list_item":
            n_counter = 0
            line = f"• {_plain_text(block)}\n"
        elif btype == "numbered_list_item":
            n_counter += 1
            line = f"{n_counter}. {_plain_text(block)}\n"
        elif btype == "divider":
            n_counter = 0
            line = "---\n"
        elif btype == "to_do":
            n_counter = 0
            checked = block.get("to_do", {}).get("checked", False)
            mark = "x" if checked else " "
            line = f"- [{mark}] {_plain_text(block)}\n"
        elif btype == "child_page":
            n_counter = 0
            title = block.get("child_page", {}).get("title", "")
            line = f"[sub-page: {title}]\n"
        elif btype == "toggle":
            n_counter = 0
            line = f"{_plain_text(block)}\n"
        else:
            n_counter = 0
            text = _plain_text(block)
            line = f"{text}\n" if text.strip() else ""

        if not line:
            continue

        if max_chars and total_chars + len(line) > max_chars:
            break  # stop at paragraph boundary

        lines.append(line)
        total_chars += len(line)

    return "".join(lines).strip()


# ── child page discovery ─────────────────────────────────────────────────────

def _list_child_pages(parent_id: str) -> list[tuple[str, str]]:
    """Return [(page_id, title), ...] for all child_page blocks under parent_id."""
    blocks = _fetch_all_blocks(parent_id)
    pages = []
    for b in blocks:
        if b.get("type") == "child_page":
            pages.append((b["id"], b.get("child_page", {}).get("title", "")))
    return pages


def _find_child_page(parent_id: str, title: str) -> str | None:
    """Return page_id of child_page whose title equals *title* (emoji prefix ignored)."""
    for page_id, page_title in _list_child_pages(parent_id):
        # Notion stores the emoji in the page icon, not the title, but some older
        # versions embed it.  Strip any leading non-ASCII run to be safe.
        clean = page_title.strip()
        # Remove a leading emoji + space, e.g. "📅 2026-05-29" → "2026-05-29"
        if len(clean) > 2 and not clean[0].isascii() and clean[1] == " ":
            clean = clean[2:]
        if clean == title:
            return page_id
    return None


# ── section extraction (Plan / Actual / General) ─────────────────────────────

def _extract_section(blocks: list[dict], heading_text: str, stop_headings: set[str]) -> str:
    """
    Return all block text between a heading matching *heading_text* and the first
    heading whose text is in *stop_headings* (or end of page).
    """
    start_idx: int | None = None
    for i, block in enumerate(blocks):
        if block.get("type") in _HEADING_TYPES and _plain_text(block).strip() == heading_text:
            start_idx = i
            break

    if start_idx is None:
        return ""

    section: list[dict] = []
    for block in blocks[start_idx + 1:]:
        if block.get("type") in _HEADING_TYPES and _plain_text(block).strip() in stop_headings:
            break
        section.append(block)

    return _blocks_to_plaintext(section)


# ── Public API ───────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_general_context() -> str:
    """Fetch and return the General Context sub-page as plain text. Cached."""
    cfg = get_config()
    ctx_page_id: str = cfg["notion_context_page_id"]
    max_chars: int = cfg.get("max_context_tokens", 600) * 4

    try:
        gc_id = _find_child_page(ctx_page_id, GENERAL_CONTEXT_TITLE)
    except Exception as exc:
        if "404" in str(exc) or "Could not find" in str(exc):
            log.error(_ACCESS_HINT)
        else:
            log.warning("Failed to list context page children: %s", exc)
        return ""

    if gc_id is None:
        log.warning("'General Context' sub-page not found under %s", ctx_page_id)
        return ""

    try:
        blocks = _fetch_all_blocks(gc_id)
    except Exception as exc:
        if "404" in str(exc) or "Could not find" in str(exc):
            log.error(_ACCESS_HINT)
        else:
            log.warning("Failed to fetch General Context blocks: %s", exc)
        return ""

    text = _blocks_to_plaintext(blocks, max_chars=max_chars)
    log.debug("load_general_context: %d chars", len(text))
    return text


def load_daily_entry(date: datetime.date) -> dict | None:
    """
    Fetch the YYYY-MM-DD sub-page and return:
        {"plan": str, "actual": str}
    Returns None if the sub-page does not exist.
    """
    cfg = get_config()
    ctx_page_id: str = cfg["notion_context_page_id"]
    date_str = str(date)

    try:
        day_id = _find_child_page(ctx_page_id, date_str)
    except Exception as exc:
        if "404" in str(exc) or "Could not find" in str(exc):
            log.error(_ACCESS_HINT)
        else:
            log.warning("Failed to list context page children: %s", exc)
        return None

    if day_id is None:
        log.debug("No daily entry found for %s", date_str)
        return None

    try:
        blocks = _fetch_all_blocks(day_id)
    except Exception as exc:
        log.warning("Failed to fetch daily entry %s: %s", date_str, exc)
        return None

    plan = _extract_section(blocks, "Plan", {"Actual"})
    actual = _extract_section(blocks, "Actual", set())

    if not plan:
        # Fallback: entire page text as plan
        log.debug("No 'Plan' heading found in %s — using full page text", date_str)
        plan = _blocks_to_plaintext(blocks)
        actual = ""

    return {"plan": plan, "actual": actual}


def load() -> dict:
    """Convenience: return {general: str, today: dict|None}."""
    return {
        "general": load_general_context(),
        "today": load_daily_entry(datetime.date.today()),
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(description="Agent context reader")
    parser.add_argument("--general", action="store_true", help="Print general context")
    parser.add_argument("--daily", metavar="DATE",
                        help="Print daily entry for DATE (YYYY-MM-DD or 'today')")
    parser.add_argument("--dry-run", action="store_true",
                        help="Pretty-print with rich (no effect on output)")
    args = parser.parse_args()

    from rich.console import Console
    from rich.panel import Panel
    console = Console()

    if args.general:
        text = load_general_context()
        if args.dry_run:
            console.print(Panel(text, title="[bold]General Context[/]", expand=False))
        else:
            print(text)

    if args.daily:
        date_str = args.daily
        if date_str.lower() == "today":
            d = datetime.date.today()
        else:
            try:
                d = datetime.date.fromisoformat(date_str)
            except ValueError:
                print(f"Invalid date: {date_str!r}", file=sys.stderr)
                sys.exit(1)
        entry = load_daily_entry(d)
        if entry is None:
            console.print(f"[yellow]No daily entry found for {d}[/]")
        elif args.dry_run:
            console.print(Panel(
                f"[bold]## Plan[/]\n{entry['plan']}\n\n[bold]## Actual[/]\n{entry['actual'] or '(empty)'}",
                title=f"[bold]Daily entry — {d}[/]", expand=False
            ))
        else:
            import json
            print(json.dumps(entry, indent=2, ensure_ascii=False))

    if not args.general and not args.daily:
        parser.print_help()


if __name__ == "__main__":
    _cli()
