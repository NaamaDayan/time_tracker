"""
Telegram webhook — reply handler for plan edits and context updates.

Design
------
handle_reply() is the primary public function. It is called by OpenClaw
(the orchestrator) whenever the user replies to a Telegram message. It is a
pure function — it detects intent, applies side effects (plan edit, Notion
update), sends the confirmation via Telegram, and returns a status string.

Intent detection (keyword-based, ordered by priority)
------------------------------------------------------
context_update  Message starts with "Update context:" or "Context:"
show_plan       Contains "show plan", "what's the plan", "plan?", or "/plan"
manual_run      Contains "run now", "trigger", or starts with "/run"
status          Contains "status" or starts with "/status"
help            Starts with "/help" or equals "help"
plan_edit       Contains any edit keyword (see _PLAN_EDIT_KEYWORDS)
unknown         None of the above → return help hint

Side effects per intent
-----------------------
plan_edit       plan_store.update_plan(text, tomorrow)
                → send_text("✓ Plan updated\n\n" + format_plan_for_telegram(plan))
                → return "✓ Plan updated"

context_update  update_general_context(content_after_prefix)
                → return "✓ Context updated in Notion."

show_plan       load_plan(tomorrow) → format_plan_for_telegram(plan)
                → send_text(plan_str)
                → return plan_str

Optional server modes (for running as a persistent listener)
------------------------------------------------------------
run_poll()      Long-poll Telegram getUpdates loop (dev mode)
run_webhook()   Minimal HTTP server receiving Telegram POSTs (production mode)
Both delegate to handle_reply() for each incoming message.

CLI
---
    python delivery/telegram_webhook.py --message "move 3 to next week"
    python delivery/telegram_webhook.py --poll
    python delivery/telegram_webhook.py --webhook [--host HOST] [--port PORT]
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import requests

from config_loader import get_config
from utils.logger import get_logger

log = get_logger("telegram_webhook")


# ── Intent detection ──────────────────────────────────────────────────────────

_PLAN_EDIT_KEYWORDS = [
    "move", "add", "remove", "replace", "swap", "change", "delete",
    "postpone", "skip", "insert", "put", "shift", "reschedule",
    "next week", "tomorrow", "priority", "drop", "push", "pull",
    "make item",
]

_CONTEXT_PREFIXES = ("update context:", "context:")
_SHOW_PLAN_TOKENS = ("show plan", "what's the plan", "plan?", "/plan")
_MANUAL_RUN_TOKENS = ("run now", "trigger", "/run")
_STATUS_TOKENS = ("status", "/status")
_HELP_TOKENS = ("/help", "help")


def _detect_intent(text: str) -> str:
    """
    Return one of: context_update | show_plan | manual_run | status |
                   help | plan_edit | unknown
    """
    t = text.strip().lower()

    # Context update — highest priority (must check prefix before edit keywords
    # because "add context" would otherwise match plan_edit)
    if t.startswith(_CONTEXT_PREFIXES):
        return "context_update"

    # Show plan
    if any(tok in t for tok in _SHOW_PLAN_TOKENS):
        return "show_plan"

    # Manual run
    if any(tok in t for tok in _MANUAL_RUN_TOKENS):
        return "manual_run"

    # Status
    if any(tok in t for tok in _STATUS_TOKENS):
        return "status"

    # Help
    if t in _HELP_TOKENS or t.startswith("/help"):
        return "help"

    # Plan edit — check for any edit keyword
    if any(kw in t for kw in _PLAN_EDIT_KEYWORDS):
        return "plan_edit"

    return "unknown"


def _extract_context_content(text: str) -> str:
    """Strip the 'Update context:' / 'Context:' prefix and return the payload."""
    stripped = text.strip()
    for prefix in ("Update context:", "Context:"):
        if stripped.lower().startswith(prefix.lower()):
            return stripped[len(prefix):].strip()
    return stripped


# ── Date helpers ──────────────────────────────────────────────────────────────

def _tomorrow() -> datetime.date:
    return datetime.date.today() + datetime.timedelta(days=1)


# ── Intent handlers ───────────────────────────────────────────────────────────

def _handle_plan_edit(text: str) -> str:
    from pipeline.plan_store import update_plan, format_plan_for_telegram
    from delivery.telegram_send import send_text

    tomorrow = _tomorrow()
    log.info("Plan edit for %s: %r", tomorrow, text[:80])

    try:
        updated = update_plan(text, tomorrow)
    except Exception as exc:
        log.error("update_plan failed: %s", exc)
        reply = f"Sorry, I couldn't apply that edit: {exc}"
        try:
            send_text(reply)
        except Exception:
            pass
        return reply

    plan_str = format_plan_for_telegram(updated)
    confirmation = f"✓ Plan updated\n\n{plan_str}"
    try:
        send_text(confirmation)
    except Exception as exc:
        log.warning("Failed to send plan confirmation: %s", exc)

    return "✓ Plan updated"


def _handle_context_update(text: str) -> str:
    from context.update_context import update_general_context

    content = _extract_context_content(text)
    if not content:
        return "Nothing to update — please provide context text after 'Context:'."

    log.info("Updating general context (%d chars)", len(content))
    try:
        update_general_context(content)
    except Exception as exc:
        log.error("update_general_context failed: %s", exc)
        return f"Failed to update Notion context: {exc}"

    return "✓ Context updated in Notion."


def _handle_show_plan() -> str:
    from pipeline.plan_store import load_plan, format_plan_for_telegram
    from delivery.telegram_send import send_text

    tomorrow = _tomorrow()
    plan = load_plan(tomorrow)
    if not plan:
        reply = f"No plan found for {tomorrow}. Run the daily pipeline first."
        try:
            send_text(reply)
        except Exception:
            pass
        return reply

    plan_str = format_plan_for_telegram(plan)
    header   = f"📅 Plan for {tomorrow}\n\n"
    full     = header + plan_str
    try:
        send_text(full)
    except Exception as exc:
        log.warning("Failed to send plan: %s", exc)

    return full


def _handle_status() -> str:
    from pipeline.plan_store import load_plan

    tomorrow = _tomorrow()
    plan     = load_plan(tomorrow)
    total    = len(plan)
    done     = sum(1 for t in plan if t.get("done"))
    reply    = f"📊 Status: {done}/{total} tasks done for {tomorrow}"
    try:
        from delivery.telegram_send import send_text
        send_text(reply)
    except Exception:
        pass
    return reply


_HELP_TEXT = (
    "Daily Agent — reply commands:\n\n"
    "• Edit the plan: \"Move 3 to next week\", \"Add: X as priority 1\", "
    "\"Replace 2 with: Y\"\n"
    "• Show plan: \"show plan\" or /plan\n"
    "• Update context: \"Context: I'm now focused on Z\"\n"
    "• Status: \"status\" or /status\n"
    "• Help: /help"
)


def _handle_help() -> str:
    try:
        from delivery.telegram_send import send_text
        send_text(_HELP_TEXT)
    except Exception:
        pass
    return _HELP_TEXT


_UNKNOWN_HINT = (
    "Didn't understand that. Try:\n"
    "• \"Move 3 to next week\"\n"
    "• \"Add: review investor deck as priority 1\"\n"
    "• \"show plan\"\n"
    "• /help for all commands"
)


# ── Main public function ──────────────────────────────────────────────────────

def handle_reply(message_text: str) -> str:
    """
    Process an incoming Telegram reply.

    Called by OpenClaw (or the poll/webhook loops below).
    Detects intent, applies side effects, sends Telegram confirmation,
    and returns a short status string for the caller.

    Parameters
    ----------
    message_text : str
        The raw text of the user's Telegram reply.

    Returns
    -------
    str
        Human-readable status: "✓ Plan updated", "✓ Context updated in Notion.",
        the plan text (for show_plan), an error message, or the help string.
    """
    text   = message_text.strip()
    intent = _detect_intent(text)
    log.info("handle_reply: intent=%s  text=%r", intent, text[:80])

    if intent == "plan_edit":
        return _handle_plan_edit(text)

    if intent == "context_update":
        return _handle_context_update(text)

    if intent == "show_plan":
        return _handle_show_plan()

    if intent == "manual_run":
        # OpenClaw triggers the pipeline; we just acknowledge here
        return "Triggering daily run is handled by OpenClaw. Use the /run claw command."

    if intent == "status":
        return _handle_status()

    if intent == "help":
        return _handle_help()

    # Unknown — send hint
    try:
        from delivery.telegram_send import send_text
        send_text(_UNKNOWN_HINT)
    except Exception:
        pass
    return _UNKNOWN_HINT


# ── Long-poll loop ────────────────────────────────────────────────────────────

def _bot_request(method: str, **kwargs) -> dict:
    cfg   = get_config()
    token = cfg["telegram_bot_token"]
    url   = f"https://api.telegram.org/bot{token}/{method}"
    resp  = requests.post(url, json=kwargs, timeout=30)
    resp.raise_for_status()
    data  = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error in {method}: {data}")
    return data


def _get_updates(offset: int | None = None) -> list[dict]:
    """Long-poll for updates (blocks up to 20 seconds)."""
    kwargs: dict = {"timeout": 20, "allowed_updates": ["message"]}
    if offset is not None:
        kwargs["offset"] = offset
    return _bot_request("getUpdates", **kwargs).get("result", [])


def run_poll(*, max_iterations: int | None = None) -> None:
    """
    Poll Telegram for updates and call handle_reply() for each message.

    *max_iterations* limits the loop (None = run forever).
    Useful for local development — no public HTTPS endpoint needed.
    """
    log.info("Starting long-poll mode (Ctrl-C to stop)…")
    offset: int | None = None
    iterations = 0

    while True:
        if max_iterations is not None and iterations >= max_iterations:
            break
        try:
            updates = _get_updates(offset)
        except KeyboardInterrupt:
            log.info("Long-poll stopped by user")
            break
        except Exception as exc:
            log.warning("getUpdates failed: %s — retrying in 5s", exc)
            time.sleep(5)
            continue

        for update in updates:
            offset = update.get("update_id", 0) + 1
            msg    = update.get("message", {})
            text   = msg.get("text", "").strip()
            if text:
                try:
                    handle_reply(text)
                except Exception as exc:
                    log.error("handle_reply error: %s", exc)

        iterations += 1


# ── Webhook server ────────────────────────────────────────────────────────────

def run_webhook(host: str = "0.0.0.0", port: int = 8443) -> None:
    """
    Start a minimal HTTP server to receive Telegram webhook POSTs.

    In production, place behind an HTTPS reverse proxy (nginx / caddy)
    or use ngrok for a public URL.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                update = json.loads(body)
                msg    = update.get("message", {})
                text   = msg.get("text", "").strip()
                if text:
                    handle_reply(text)
            except Exception as exc:
                log.error("Webhook handler error: %s", exc)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, fmt: str, *args) -> None:  # type: ignore[override]
            log.debug(fmt, *args)

    server = HTTPServer((host, port), _Handler)
    log.info("Webhook server listening on %s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Webhook server stopped")
        server.shutdown()


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Telegram reply handler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python delivery/telegram_webhook.py --message 'move 3 to next week'\n"
            "  python delivery/telegram_webhook.py --message 'show plan'\n"
            "  python delivery/telegram_webhook.py --poll\n"
            "  python delivery/telegram_webhook.py --webhook --port 8443\n"
        ),
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--message", metavar="TEXT",
        help="Simulate an incoming reply and print the result (no Telegram needed)",
    )
    mode.add_argument(
        "--poll", action="store_true",
        help="Long-poll mode — poll Telegram for updates (dev/local)",
    )
    mode.add_argument(
        "--webhook", action="store_true",
        help="HTTP webhook server mode",
    )

    parser.add_argument("--host",  default="0.0.0.0", help="Webhook bind host")
    parser.add_argument("--port",  type=int, default=8443, help="Webhook port")
    parser.add_argument(
        "--no-send", action="store_true",
        help="With --message: detect intent and print result but do NOT send Telegram",
    )

    args = parser.parse_args()

    if args.message:
        if args.no_send:
            # Dry-run: just detect intent, no side effects
            intent = _detect_intent(args.message)
            print(f"Intent: {intent}")
            print(f"Text:   {args.message!r}")
        else:
            result = handle_reply(args.message)
            print(result)

    elif args.poll:
        run_poll()

    elif args.webhook:
        run_webhook(host=args.host, port=args.port)


if __name__ == "__main__":
    _cli()
