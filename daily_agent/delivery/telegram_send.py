"""
Telegram delivery.

Formats the daily summary result into a Telegram-friendly message and sends it
via the Bot API using requests directly (no python-telegram-bot required).

Uses Telegram Markdown v1 (parse_mode="Markdown"), NOT MarkdownV2.
  • *bold*        → bold
  • _italic_      → italic
  • `code`        → monospace
  • No escaping needed for most punctuation — only _ and * in user content

Public API
----------
send_summary(result: dict, date: datetime.date) -> None
    Format and send the full daily summary + plan.
    Splits at the 📅 plan section boundary if > telegram_max_chars.

send_text(text: str) -> None
    Send a plain text message (used for confirmations, errors, plan previews).

send_error(error: str | Exception) -> None
    Send a concise error notification.

Backward-compat aliases
-----------------------
send_daily_summary  = send_summary
send_message        = send_text
send_plan_updated   — accepts a plan list, formats via plan_store and calls send_text

CLI
---
    python delivery/telegram_send.py --test
        Load tests/fixture_day.json, format a sample result, and send to verify
        bot token + chat_id are working.

    python delivery/telegram_send.py --preview
        Print the formatted message to stdout (no send).
"""

from __future__ import annotations

import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import requests

from config_loader import get_config
from utils.logger import get_logger

log = get_logger("telegram_send")

_PRIORITY_LABELS = {"high": "HIGH", "medium": "MED", "low": "LOW"}
_PRIORITY_ORDER  = {"high": 0, "medium": 1, "low": 2}

# Split point: if the full message is too long, send everything BEFORE this
# marker as message 1, and from this marker onward as message 2.
_PLAN_SPLIT_MARKER = "📅 *"


# ── Content escaping (Markdown v1) ────────────────────────────────────────────

def _esc(text: str) -> str:
    """
    Escape user-generated content for Telegram Markdown v1.

    Only _ and * need escaping — paired underscores/asterisks would otherwise
    trigger italic/bold formatting in the middle of task names.
    """
    return text.replace("_", r"\_").replace("*", r"\*")


# ── Message formatting ────────────────────────────────────────────────────────

def _fmt_minutes(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _format_summary(result: dict, date: datetime.date) -> str:
    """
    Build the full Telegram message using the CLAUDE.md template.

    Returns a string ready to POST with parse_mode=Markdown.
    """
    tomorrow = date + datetime.timedelta(days=1)
    parts: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    parts.append(f"📊 *Daily Summary — {date}*")
    parts.append("")

    # ── Summary paragraph(s) ─────────────────────────────────────────────────
    summary = result.get("summary", "").strip()
    if summary:
        for para in summary.split("\n\n"):
            para = para.strip()
            if para:
                parts.append(_esc(para))
                parts.append("")

    # ── Key Wins ─────────────────────────────────────────────────────────────
    highlights = result.get("highlights", [])
    if highlights:
        parts.append("✅ *Key Wins*")
        for h in highlights[:5]:
            parts.append(f"• {_esc(h)}")
        parts.append("")

    # ── Time Split ───────────────────────────────────────────────────────────
    time_breakdown = result.get("time_breakdown", [])
    if time_breakdown:
        parts.append("🕐 *Time Split*")
        for item in time_breakdown[:6]:
            app  = _esc(item.get("app", "?"))
            cat  = _esc(item.get("category", ""))
            mins = item.get("minutes", 0)
            label = f"{app} / {cat}" if cat else app
            parts.append(f"• {label}: {_fmt_minutes(mins)}")
        parts.append("")

    # ── Tomorrow's Plan ───────────────────────────────────────────────────────
    plan = result.get("tomorrow_plan", [])
    if plan:
        parts.append(f"📅 *Tomorrow's Plan — {tomorrow}*")
        sorted_plan = sorted(
            plan,
            key=lambda t: (_PRIORITY_ORDER.get(t.get("priority", "low"), 2),
                           t.get("id", 99)),
        )
        for i, task in enumerate(sorted_plan, 1):
            pri_key = task.get("priority", "low")
            pri     = _PRIORITY_LABELS.get(pri_key, "???")
            name    = _esc(task.get("task", ""))
            ctx     = _esc(task.get("context", ""))
            ctx_str = f" — {ctx}" if ctx else ""
            parts.append(f"{i}. [{pri}] {name}{ctx_str}")
        parts.append("")

    # ── Blockers ──────────────────────────────────────────────────────────────
    blockers = result.get("blockers", [])
    if blockers:
        parts.append("⚠️ *Watch Out For*")
        for b in blockers[:3]:
            parts.append(f"• {_esc(b)}")
        parts.append("")

    # ── Footer / edit hint ────────────────────────────────────────────────────
    parts.append('_Reply to edit the plan. Examples:_')
    parts.append('_"Move 3 to next week"_')
    parts.append('_"Add: review investor deck as priority 1"_')
    parts.append('_"Replace 4 with: call with Fernando"_')

    return "\n".join(parts)


def _split_at_plan(message: str, max_chars: int) -> list[str]:
    """
    Split *message* into at most two parts at the plan section boundary.

    If the message fits within *max_chars*, return it as-is.
    Otherwise split at the first occurrence of _PLAN_SPLIT_MARKER so the
    summary + highlights land in part 1 and the plan + footer in part 2.
    If no split marker is found, fall back to a hard line-boundary split.
    """
    if len(message) <= max_chars:
        return [message]

    idx = message.find(_PLAN_SPLIT_MARKER)
    if idx > 0:
        part1 = message[:idx].rstrip()
        part2 = message[idx:]
        if part1 and part2:
            log.info("Message split at plan boundary (%d + %d chars)",
                     len(part1), len(part2))
            return [part1, part2]

    # Fallback: split at last newline before max_chars
    cut = message.rfind("\n", 0, max_chars)
    if cut < 0:
        cut = max_chars
    log.warning("Message split at line boundary (no plan marker found)")
    return [message[:cut], message[cut:].lstrip("\n")]


# ── Bot API call ──────────────────────────────────────────────────────────────

def _send_raw(text: str, *, parse_mode: str = "Markdown") -> dict:
    """
    POST a message via the Telegram Bot API.

    Raises requests.HTTPError on non-2xx HTTP responses, or RuntimeError if
    Telegram returns ok=false.
    """
    cfg     = get_config()
    token   = cfg["telegram_bot_token"]
    chat_id = cfg["telegram_chat_id"]
    url     = f"https://api.telegram.org/bot{token}/sendMessage"

    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    log.debug("Telegram message sent: message_id=%s",
              data.get("result", {}).get("message_id"))
    return data


def _send_md(text: str) -> None:
    """
    Send *text* with Markdown v1. Falls back to plain text on parse error.
    """
    try:
        _send_raw(text, parse_mode="Markdown")
    except requests.HTTPError as exc:
        # 400 with "can't parse entities" → retry as plain text
        if exc.response is not None and exc.response.status_code == 400:
            log.warning("Markdown parse error — retrying as plain text: %s", exc)
            plain = text.replace("*", "").replace("_", "").replace("`", "")
            _send_raw(plain, parse_mode="")
        else:
            raise


# ── Public API ────────────────────────────────────────────────────────────────

def send_summary(result: dict, date: datetime.date) -> None:
    """
    Format and send the full daily summary.

    Splits at the plan section boundary if the message exceeds
    config["telegram_max_chars"] (default 4000).
    """
    cfg      = get_config()
    max_chars: int = cfg.get("telegram_max_chars", 4000)

    message = _format_summary(result, date)
    parts   = _split_at_plan(message, max_chars)

    log.info("Sending daily summary: %d chars, %d part(s)", len(message), len(parts))
    for i, part in enumerate(parts, 1):
        try:
            _send_md(part)
            log.info("Sent part %d/%d (%d chars)", i, len(parts), len(part))
        except Exception as exc:
            log.error("Failed to send summary part %d/%d: %s", i, len(parts), exc)
            raise


def send_text(text: str) -> None:
    """
    Send a plain text message — no Markdown formatting applied.

    Used for confirmations, plan previews, error notices.
    """
    cfg       = get_config()
    max_chars: int = cfg.get("telegram_max_chars", 4000)

    if len(text) <= max_chars:
        parts = [text]
    else:
        # Split at line boundary
        parts = []
        while text:
            cut = text.rfind("\n", 0, max_chars)
            if cut < 1:
                cut = max_chars
            parts.append(text[:cut])
            text = text[cut:].lstrip("\n")

    for part in parts:
        try:
            _send_raw(part, parse_mode="")
            log.info("Sent plain text (%d chars)", len(part))
        except Exception as exc:
            log.error("Failed to send Telegram message: %s", exc)
            raise


def send_error(error: str | Exception) -> None:
    """Send a concise error notification."""
    msg = f"⚠️ Daily Agent error: {error}"
    try:
        send_text(msg)
    except Exception as exc:
        log.error("Failed to send error notification: %s", exc)


# ── Backward-compat aliases ───────────────────────────────────────────────────

def send_daily_summary(result: dict, date: datetime.date) -> None:
    """Alias for send_summary (backward compatibility)."""
    send_summary(result, date)


def send_message(text: str) -> None:
    """Alias for send_text (backward compatibility)."""
    send_text(text)


def send_plan_updated(plan: list[dict]) -> None:
    """
    Send a compact plan-updated confirmation.

    Formats the plan via plan_store.format_plan_for_telegram and sends it as
    plain text with a '✓ Plan updated' header.
    """
    from pipeline.plan_store import format_plan_for_telegram
    body = format_plan_for_telegram(plan)
    send_text(f"✓ Plan updated\n\n{body}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def _make_fixture_result() -> tuple[dict, datetime.date]:
    """Load tests/fixture_day.json and construct a fake summarizer result from it."""
    import json as _json

    fixture_path = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixture_day.json"
    fixture = _json.loads(fixture_path.read_text(encoding="utf-8"))
    date = datetime.date.fromisoformat(fixture["date"])

    result = {
        "summary": (
            "Spent the day designing and building the two-stage summarizer pipeline "
            "for the daily agent. Completed Stage 1A (Cursor pre-summarizer using "
            "claude-haiku) and Stage 1B (timeline builder merging ActivityWatch events "
            "with typing entries). Attended an Architecture Review meeting where key "
            "decisions were made on model selection and token budget strategy."
        ),
        "highlights": [
            "Designed and implemented two-stage summarizer pipeline",
            "Resolved Cursor pre-summary model: claude-haiku for Stage 1A",
            "Settled timeline merge gap threshold at 60 seconds",
            "Architecture Review: team aligned on token budget cascade strategy",
        ],
        "tomorrow_plan": [
            {
                "id": 1, "priority": "high",
                "task": "Implement _render_timeline_section with token budget enforcement",
                "context": "4-step cascade: drop charcount → truncate typing → drop summary → hard cut",
            },
            {
                "id": 2, "priority": "high",
                "task": "Wire collect_activitywatch.get_events_date() into summarizer",
                "context": "Need raw_events for timeline builder",
            },
            {
                "id": 3, "priority": "medium",
                "task": "Test full pipeline end-to-end with fixture_day.json",
                "context": "Verify token counts and JSON parse",
            },
            {
                "id": 4, "priority": "medium",
                "task": "Add Notion daily entry write-back in run_daily.py",
                "context": "Call update_context after summarize",
            },
            {
                "id": 5, "priority": "low",
                "task": "Enable cron job at 20:00",
                "context": "Automate daily run once pipeline is stable",
            },
        ],
        "time_breakdown": [
            {"app": "Cursor",         "minutes": 135, "category": "dev"},
            {"app": "Google Chrome",  "minutes":  65, "category": "research"},
            {"app": "Zoom",           "minutes":  55, "category": "meetings"},
            {"app": "Notion",         "minutes":  20, "category": "writing"},
        ],
        "blockers": [
            "ActivityWatch raw_events integration not yet tested with real data",
        ],
    }
    return result, date


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Telegram send — test and preview",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Load tests/fixture_day.json and SEND the formatted message via Telegram",
    )
    parser.add_argument(
        "--preview", action="store_true",
        help="Load tests/fixture_day.json, print the formatted message, do NOT send",
    )
    parser.add_argument(
        "--text", metavar="MSG",
        help="Send a plain text message (quick sanity-check for bot token/chat_id)",
    )
    args = parser.parse_args()

    if args.text:
        send_text(args.text)
        print(f"✓ Sent: {args.text!r}")

    elif args.preview or args.test:
        result, date = _make_fixture_result()
        cfg      = get_config()
        max_chars: int = cfg.get("telegram_max_chars", 4000)
        message  = _format_summary(result, date)
        parts    = _split_at_plan(message, max_chars)

        if args.preview:
            for i, part in enumerate(parts, 1):
                if len(parts) > 1:
                    print(f"━━━ Part {i}/{len(parts)} ({len(part)} chars) ━━━")
                print(part)
            print(f"\n[{len(message)} chars total, {len(parts)} part(s)]")
        else:
            print(f"Sending {len(parts)} part(s) ({len(message)} chars total)…")
            send_summary(result, date)
            print("✓ Sent.")

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
