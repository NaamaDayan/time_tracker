"""
Daily pipeline orchestrator.

Called at 20:00 daily (by cron or OpenClaw).

Execution order
---------------
1. Collect  — 5 collectors run in parallel (ThreadPoolExecutor)
              typing, ActivityWatch, Cursor, Notion meetings, context
2. Summarize — two-stage Claude pipeline (Cursor pre-summary → timeline → summary)
3. Store     — save tomorrow's plan to plan_store
4. Notion    — write tomorrow's plan + today's actual (both best-effort)
5. Deliver   — send Telegram message (or print in --dry-run)
6. Log       — elapsed time, exit code

Error handling
--------------
• Individual collector failures are isolated — pipeline continues with empty data
• Summarizer hard failure (no JSON returned) → save pending/, exit 1
• Any unhandled exception → save pending/, send Telegram error, exit 1
• Delivery failure → plan already saved, exit 2

CLI
---
    python pipeline/run_daily.py                    # today, send Telegram
    python pipeline/run_daily.py --dry-run          # today, print only (no save, no send)
    python pipeline/run_daily.py --send             # explicit send (same as default)
    python pipeline/run_daily.py --date 2026-05-28  # specific date
    python pipeline/run_daily.py --date 2026-05-28 --send   # rerun + resend
    python pipeline/run_daily.py --collect-only     # run collectors, print JSON, exit

Exit codes
----------
0  success
1  pipeline error (collect/summarize failed; raw data saved to pending/)
2  delivery error (plan saved; Telegram send failed)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import pathlib
import sys
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from config_loader import get_config
from utils.logger import get_logger

log = get_logger("run_daily")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pending_dir() -> pathlib.Path:
    cfg = get_config()
    d = pathlib.Path(cfg.get("pending_dir", "~/.daily-agent/pending")).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_pending(date: datetime.date, data: dict) -> pathlib.Path:
    """Persist raw collected data so a failed run can be retried manually."""
    path = _pending_dir() / f"{date}.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    log.info("Raw data saved to pending: %s", path)
    return path


def _format_plan_as_bullets(plan: list[dict]) -> str:
    """
    Render a plan task list as plain bullet text for writing to Notion.

    Example:
        • [HIGH] Implement timeline builder — critical path
        • [MED] Write tests — needed before merge
    """
    lines: list[str] = []
    for t in plan:
        pri  = t.get("priority", "medium").upper()
        task = t.get("task", "")
        ctx  = t.get("context", "")
        ctx_str = f" — {ctx}" if ctx else ""
        lines.append(f"• [{pri}] {task}{ctx_str}")
    return "\n".join(lines)


# ── Stage 1: Collect (parallel) ───────────────────────────────────────────────

_COLLECTOR_DEFAULTS: dict[str, object] = {
    "typing":        [],
    "activitywatch": {},
    "cursor":        [],
    "meetings":      [],
    "context":       {"general": "", "today": None},
}


def _collect_parallel(date: datetime.date) -> dict:
    """
    Run all 5 collectors concurrently.

    Each collector failure is isolated: a warning is logged and the pipeline
    continues with an empty default for that data source.
    """
    # ── nested collector functions (imports inside each — fail independently) ──

    def do_typing():
        from collectors.collect_typing import load_date
        r = load_date(date)
        log.info("Typing: %d entries", len(r))
        return "typing", r

    def do_activitywatch():
        from collectors.collect_activitywatch import get_date
        r = get_date(date)
        log.info("ActivityWatch: %d active minutes",
                 r.get("total_active_minutes", 0))
        return "activitywatch", r

    def do_cursor():
        from collectors.collect_cursor import get_date
        r = get_date(date)
        log.info("Cursor: %d sessions", len(r))
        return "cursor", r

    def do_meetings():
        from collectors.collect_notion_meetings import get_date
        r = get_date(date)
        log.info("Meetings: %d", len(r))
        return "meetings", r

    def do_context():
        from context.fetch_context import load
        r = load()
        log.info("Context: general=%s, today=%s",
                 bool(r.get("general")), bool(r.get("today")))
        return "context", r

    tasks = [do_typing, do_activitywatch, do_cursor, do_meetings, do_context]

    log.info("=== Stage 1: Collect (%s) — 5 collectors in parallel ===", date)
    t0 = time.monotonic()

    data: dict = {"date": date}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fn): fn.__name__ for fn in tasks}
        for fut in concurrent.futures.as_completed(futures):
            fn_name = futures[fut]
            try:
                key, value = fut.result()
                data[key] = value
            except Exception as exc:
                # Map function name → data key for the default
                key = fn_name.removeprefix("do_")
                log.warning("Collector '%s' failed: %s", key, exc)
                data[key] = _COLLECTOR_DEFAULTS[key]

    log.info("Collection done in %.1fs", time.monotonic() - t0)
    return data


# ── Stage 2: Summarize ────────────────────────────────────────────────────────

def _summarize(data: dict) -> dict:
    """
    Run the two-stage summarizer pipeline.

    Returns the structured result dict (may contain "error" key on soft failure).
    Raises ValueError on hard JSON-parse failure.
    """
    log.info("=== Stage 2: Summarize ===")
    from pipeline.summarizer import summarize as do_summarize

    result = do_summarize(
        typing_entries  = data.get("typing", []),
        activitywatch   = data.get("activitywatch") or {},
        cursor_sessions = data.get("cursor", []),
        meetings        = data.get("meetings", []),
        context         = data.get("context") or {},
        date            = data["date"],
    )

    if "error" in result:
        log.error("Summarizer returned error: %s", result["error"])
    else:
        log.info(
            "Summarize OK: %d plan tasks, %d highlights, %d blockers",
            len(result.get("tomorrow_plan", [])),
            len(result.get("highlights", [])),
            len(result.get("blockers", [])),
        )
    return result


# ── Stage 3: Store ────────────────────────────────────────────────────────────

def _store(result: dict, date: datetime.date) -> None:
    """Save tomorrow's plan to plan_store (non-fatal on failure)."""
    log.info("=== Stage 3: Store ===")
    from pipeline.plan_store import save_plan
    tomorrow = date + datetime.timedelta(days=1)
    try:
        save_plan(
            plan           = result.get("tomorrow_plan", []),
            date           = tomorrow,
            summary        = result.get("summary", ""),
            highlights     = result.get("highlights", []),
            time_breakdown = result.get("time_breakdown", []),
            blockers       = result.get("blockers", []),
            source_date    = date,
        )
        log.info("Plan stored for %s", tomorrow)
    except Exception as exc:
        log.error("plan_store.save_plan failed: %s", exc)
        # Non-fatal — continue to Notion write + delivery


# ── Stage 4: Notion writes ────────────────────────────────────────────────────

def _write_notion(result: dict, date: datetime.date) -> None:
    """
    Write to Notion (both entries are best-effort — failures do NOT abort delivery).

    1. Tomorrow's plan → upsert_daily_entry(tomorrow, plan=bullet_text)
    2. Today's actual  → upsert_daily_entry(date,     actual=summary)
    """
    from context.update_context import upsert_daily_entry

    tomorrow = date + datetime.timedelta(days=1)

    # Write tomorrow's plan
    plan = result.get("tomorrow_plan", [])
    if plan:
        plan_text = _format_plan_as_bullets(plan)
        try:
            upsert_daily_entry(tomorrow, plan=plan_text)
            log.info("Notion: wrote plan for %s (%d tasks)", tomorrow, len(plan))
        except Exception as exc:
            log.warning("Notion plan write failed for %s: %s", tomorrow, exc)

    # Write today's actual summary
    summary = result.get("summary", "").strip()
    if summary:
        try:
            upsert_daily_entry(date, actual=summary)
            log.info("Notion: wrote actual for %s", date)
        except Exception as exc:
            log.warning("Notion actual write failed for %s: %s", date, exc)


# ── Stage 5: Deliver ──────────────────────────────────────────────────────────

def _deliver(result: dict, date: datetime.date) -> bool:
    """Format and send the Telegram summary. Returns True on success."""
    log.info("=== Stage 5: Deliver ===")
    try:
        from delivery.telegram_send import send_summary
        send_summary(result, date)
        log.info("Telegram delivery OK")
        return True
    except Exception as exc:
        log.error("Telegram delivery failed: %s\n%s", exc, traceback.format_exc())
        return False


def _print_result(result: dict, date: datetime.date) -> None:
    """Print the formatted Telegram message to stdout (dry-run mode)."""
    from delivery.telegram_send import _format_summary
    formatted = _format_summary(result, date)
    try:
        from rich.console import Console
        from rich.rule import Rule
        console = Console()
        console.print(Rule(f"[bold green]Daily Agent — {date}  (dry-run)[/]"))
        console.print(formatted)
        console.print(Rule())
        console.print(
            f"[dim]{len(formatted)} chars  |  "
            f"{len(result.get('tomorrow_plan', []))} plan tasks  |  "
            f"{len(result.get('highlights', []))} highlights[/]"
        )
    except ImportError:
        print(f"{'─' * 60}")
        print(formatted)
        print(f"{'─' * 60}")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(
    date: datetime.date,
    *,
    dry_run: bool = False,
    skip_notion_write: bool = False,
) -> int:
    """
    Execute the full daily pipeline for *date*.

    Parameters
    ----------
    date              : The date being summarised (usually today).
    dry_run           : If True — collect + summarise but do NOT save plan,
                        write Notion, or send Telegram. Print result instead.
    skip_notion_write : If True — skip Notion writes (plan + actual).

    Returns exit code: 0 = success, 1 = pipeline error, 2 = delivery error.
    """
    t_pipeline = time.monotonic()
    log.info("=" * 60)
    log.info("Daily Agent pipeline  date=%s  dry_run=%s", date, dry_run)
    log.info("=" * 60)

    data: dict | None = None

    try:
        # ── 1. Collect ────────────────────────────────────────────────────────
        data = _collect_parallel(date)

        # ── 2. Summarize ──────────────────────────────────────────────────────
        try:
            result = _summarize(data)
        except ValueError as exc:
            # Hard failure: Claude returned un-parseable JSON
            log.error("Summarizer hard failure: %s", exc)
            _save_pending(date, {"collected": data, "error": str(exc)})
            try:
                from delivery.telegram_send import send_error
                send_error(f"Summarizer failed: {exc}")
            except Exception:
                pass
            return 1

        if "error" in result and not result.get("summary"):
            # Soft failure with no usable output
            _save_pending(date, {"collected": data, "error": result.get("error")})
            log.error("Pipeline aborted — raw data saved for retry")
            try:
                from delivery.telegram_send import send_error
                send_error(f"Pipeline error: {result.get('error')}")
            except Exception:
                pass
            return 1

        # ── 3. Store ──────────────────────────────────────────────────────────
        if not dry_run:
            _store(result, date)

        # ── 4. Notion writes (best-effort) ────────────────────────────────────
        if not dry_run and not skip_notion_write:
            log.info("=== Stage 4: Notion writes ===")
            _write_notion(result, date)

        # ── 5. Deliver ────────────────────────────────────────────────────────
        if dry_run:
            log.info("=== Stage 5: Deliver (dry-run — printing to stdout) ===")
            _print_result(result, date)
            exit_code = 0
        else:
            ok = _deliver(result, date)
            exit_code = 0 if ok else 2

        elapsed = time.monotonic() - t_pipeline
        log.info("Pipeline finished in %.1fs  exit_code=%d", elapsed, exit_code)
        return exit_code

    except Exception as exc:
        # Catch-all: unhandled exception anywhere in the pipeline
        log.error(
            "Unhandled pipeline exception: %s\n%s", exc, traceback.format_exc()
        )
        payload = {"error": str(exc), "traceback": traceback.format_exc()}
        if data is not None:
            payload["collected"] = data
        _save_pending(date, payload)
        try:
            from delivery.telegram_send import send_error
            send_error(f"Unhandled error: {exc}")
        except Exception:
            pass
        return 1


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Daily Agent pipeline runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--date", default="today",
        help="Date to run for (YYYY-MM-DD or 'today'). Default: today",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help=(
            "Collect + summarize but do NOT save plan, write Notion, "
            "or send Telegram. Print the formatted message instead."
        ),
    )
    parser.add_argument(
        "--send", action="store_true",
        help="Explicitly send via Telegram (same as default; provided for clarity)",
    )
    parser.add_argument(
        "--skip-notion-write", action="store_true",
        help="Skip Notion daily-entry writes (plan + actual)",
    )
    parser.add_argument(
        "--collect-only", action="store_true",
        help="Run collectors only, print JSON to stdout, and exit",
    )
    args = parser.parse_args()

    date = (
        datetime.date.today()
        if args.date == "today"
        else datetime.date.fromisoformat(args.date)
    )

    if args.collect_only:
        data = _collect_parallel(date)
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    exit_code = run(
        date,
        dry_run           = args.dry_run,
        skip_notion_write = args.skip_notion_write,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    _cli()
