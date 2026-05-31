"""
Context writer.

Updates the "Daily Plans - Plan VS Actual" Notion page.

  update_general_context(text)          → append timestamped paragraph to General Context
  upsert_daily_entry(date, plan, actual) → create or update YYYY-MM-DD sub-page
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from config_loader import get_config
from utils.logger import get_logger
from utils.notion_client import get_notion

log = get_logger("update_context")

_HEADING_TYPES = {"heading_1", "heading_2", "heading_3"}
GENERAL_CONTEXT_TITLE = "General Context"


# ── Block construction helpers ────────────────────────────────────────────────

def _rich_text(content: str) -> list[dict]:
    return [{"type": "text", "text": {"content": content}}]


def _paragraph(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _rich_text(text)}}


def _heading2(text: str) -> dict:
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": _rich_text(text)}}


def _bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _rich_text(text)}}


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _text_to_blocks(text: str) -> list[dict]:
    """
    Convert a plain text string to Notion blocks.
    Multi-line → one bulleted_list_item per non-empty line.
    Single line → one paragraph block.
    """
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return [_paragraph("")]
    if len(lines) == 1:
        return [_paragraph(lines[0])]
    return [_bullet(ln) for ln in lines]


# ── Shared block fetcher ──────────────────────────────────────────────────────

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


def _plain_text(block: dict) -> str:
    btype = block.get("type", "")
    return "".join(
        s.get("plain_text", "")
        for s in block.get(btype, {}).get("rich_text", [])
    )


# ── Child page discovery / creation ─────────────────────────────────────────

def _find_child_page(parent_id: str, title: str) -> str | None:
    notion = get_notion()
    blocks = _fetch_all_blocks(parent_id)
    for b in blocks:
        if b.get("type") == "child_page":
            page_title = b.get("child_page", {}).get("title", "")
            if title in page_title or page_title == title:
                return b["id"]
    return None


def _find_or_create_daily_page(date: datetime.date) -> str:
    """Return the page_id for the YYYY-MM-DD sub-page, creating it if necessary."""
    cfg = get_config()
    ctx_page_id: str = cfg["notion_context_page_id"]
    date_str = str(date)

    try:
        existing = _find_child_page(ctx_page_id, date_str)
    except Exception as exc:
        if "404" in str(exc) or "Could not find" in str(exc):
            raise RuntimeError(
                f"Notion 404 — the integration lacks access to the context page.\n"
                "Fix: open 'Daily Plans - Plan VS Actual' in Notion → ··· → Connections\n"
                "→ add your integration, then retry."
            ) from exc
        raise

    if existing:
        log.debug("Found existing daily page for %s: %s", date_str, existing)
        return existing

    # Create the page with full Plan / Actual structure
    notion = get_notion()
    new_page = notion.pages.create(
        parent={"page_id": ctx_page_id},
        icon={"type": "emoji", "emoji": "📅"},
        properties={
            "title": {"title": _rich_text(date_str)}
        },
        children=[
            _heading2("Plan"),
            _bullet("[The agent will write tomorrow's plan here automatically at 20:00]"),
            _bullet("[You can also edit this manually before the day starts]"),
            _bullet("[Format: one task per bullet, keep it concrete]"),
            _heading2("Actual"),
            _paragraph("Written by the agent at end of day — do not edit manually."),
        ],
    )
    page_id: str = new_page["id"]
    log.info("Created daily page for %s: %s", date_str, page_id)
    return page_id


# ── Section update helpers ────────────────────────────────────────────────────

def _find_heading_block(blocks: list[dict], heading_text: str) -> dict | None:
    """Return the first heading block whose plain text matches heading_text."""
    for b in blocks:
        if b.get("type") in _HEADING_TYPES and _plain_text(b).strip() == heading_text:
            return b
    return None


def _blocks_between_headings(blocks: list[dict],
                              start_heading_text: str,
                              stop_heading_texts: set[str]) -> list[dict]:
    """
    Return the (non-heading) blocks between start_heading and the next heading
    whose text is in stop_heading_texts (exclusive of both heading blocks).
    """
    in_section = False
    result: list[dict] = []
    for b in blocks:
        if b.get("type") in _HEADING_TYPES:
            text = _plain_text(b).strip()
            if text == start_heading_text:
                in_section = True
                continue
            if in_section and text in stop_heading_texts:
                break
        elif in_section:
            result.append(b)
    return result


def _replace_section_content(page_id: str,
                              heading_text: str,
                              stop_headings: set[str],
                              new_blocks: list[dict]) -> None:
    """
    Delete existing content blocks in a section and insert new ones after the heading.
    The heading block itself is never deleted.
    """
    notion = get_notion()
    blocks = _fetch_all_blocks(page_id)

    heading_block = _find_heading_block(blocks, heading_text)
    if heading_block is None:
        log.warning("Heading '%s' not found in page %s — appending at end", heading_text, page_id)
        notion.blocks.children.append(block_id=page_id, children=new_blocks)
        return

    # Delete existing content in this section
    old_content = _blocks_between_headings(blocks, heading_text, stop_headings)
    for b in old_content:
        try:
            notion.blocks.delete(block_id=b["id"])
        except Exception as exc:
            log.warning("Failed to delete block %s: %s", b["id"], exc)

    # Append new content after the heading block
    notion.blocks.children.append(
        block_id=page_id,
        after=heading_block["id"],
        children=new_blocks,
    )
    log.debug("Replaced section '%s' with %d new blocks", heading_text, len(new_blocks))


# ── Public API ───────────────────────────────────────────────────────────────

def update_general_context(text: str) -> None:
    """Append a timestamped paragraph to the General Context sub-page."""
    cfg = get_config()
    ctx_page_id: str = cfg["notion_context_page_id"]

    try:
        gc_id = _find_child_page(ctx_page_id, GENERAL_CONTEXT_TITLE)
    except Exception as exc:
        if "404" in str(exc) or "Could not find" in str(exc):
            raise RuntimeError(
                f"Notion 404 — the integration lacks access to the context page.\n"
                "Fix: open 'Daily Plans - Plan VS Actual' in Notion → ··· → Connections\n"
                "→ add your integration, then retry."
            ) from exc
        raise

    if gc_id is None:
        raise RuntimeError(
            f"'General Context' sub-page not found under {ctx_page_id}. "
            "Run context/init_context_page.py first."
        )

    notion = get_notion()
    timestamp = datetime.datetime.now(tz=datetime.timezone.utc).isoformat(timespec="seconds")
    entry = f"[{timestamp}] {text.strip()}"

    notion.blocks.children.append(
        block_id=gc_id,
        children=[_divider(), _paragraph(entry)],
    )
    log.info("Appended to General Context: %s", entry[:80])
    print(f"✓ General Context updated: {entry[:80]}")


def upsert_daily_entry(
    date: datetime.date,
    plan: str | None = None,
    actual: str | None = None,
) -> None:
    """Create or update the YYYY-MM-DD sub-page. Replaces the named sections."""
    if plan is None and actual is None:
        raise ValueError("At least one of plan or actual must be provided")

    page_id = _find_or_create_daily_page(date)

    if plan is not None:
        _replace_section_content(
            page_id,
            heading_text="Plan",
            stop_headings={"Actual"},
            new_blocks=_text_to_blocks(plan),
        )
        log.info("Updated Plan for %s", date)
        print(f"✓ Plan updated for {date}")

    if actual is not None:
        _replace_section_content(
            page_id,
            heading_text="Actual",
            stop_headings=set(),
            new_blocks=_text_to_blocks(actual),
        )
        log.info("Updated Actual for %s", date)
        print(f"✓ Actual updated for {date}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def _parse_date(s: str) -> datetime.date:
    if s.lower() == "today":
        return datetime.date.today()
    return datetime.date.fromisoformat(s)


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Agent context writer")
    sub = parser.add_subparsers(dest="cmd")

    # --general TEXT
    g = sub.add_parser("general", help="Append text to General Context")
    g.add_argument("text", help="Text to append")

    # --plan DATE TEXT
    p = sub.add_parser("plan", help="Set plan for a date")
    p.add_argument("date", help="YYYY-MM-DD or 'today'")
    p.add_argument("text", help="Plan text (use \\n for multiple tasks)")

    # --actual DATE TEXT
    a = sub.add_parser("actual", help="Set actual for a date")
    a.add_argument("date", help="YYYY-MM-DD or 'today'")
    a.add_argument("text", help="Actual text")

    # Also support flag-style: --general / --plan / --actual
    # to match the spec's CLI examples
    parser.add_argument("--general", metavar="TEXT", help="Append to General Context")
    parser.add_argument("--plan", nargs=2, metavar=("DATE", "TEXT"),
                        help="Set plan: --plan DATE 'text'")
    parser.add_argument("--actual", nargs=2, metavar=("DATE", "TEXT"),
                        help="Set actual: --actual DATE 'text'")

    args = parser.parse_args()

    # Handle flag-style usage
    if args.general:
        update_general_context(args.general.replace("\\n", "\n"))
        return
    if args.plan:
        date = _parse_date(args.plan[0])
        upsert_daily_entry(date, plan=args.plan[1].replace("\\n", "\n"))
        return
    if args.actual:
        date = _parse_date(args.actual[0])
        upsert_daily_entry(date, actual=args.actual[1].replace("\\n", "\n"))
        return

    # Handle subcommand-style usage
    if args.cmd == "general":
        update_general_context(args.text.replace("\\n", "\n"))
    elif args.cmd == "plan":
        upsert_daily_entry(_parse_date(args.date), plan=args.text.replace("\\n", "\n"))
    elif args.cmd == "actual":
        upsert_daily_entry(_parse_date(args.date), actual=args.text.replace("\\n", "\n"))
    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
