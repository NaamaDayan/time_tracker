#!/usr/bin/env python3
"""
Daily Agent — pre-flight health check.

Run this before the first real pipeline execution to verify all
external dependencies are configured and reachable.

    python health_check.py

Each check prints ✅ on success or ❌ on failure with an error hint.

Exit code: 0 if every check passes, 1 if any check fails.
"""

from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_REQUIRED_CONFIG_KEYS = [
    "anthropic_api_key",
    "telegram_bot_token",
    "telegram_chat_id",
    "notion_api_key",
    "notion_meetings_db_id",
    "notion_context_page_id",
    "typing_log_dir",
    "plans_dir",
]

_RESULTS: list[tuple[str, bool, str]] = []  # (label, passed, detail)


def _check(label: str, fn) -> bool:
    """Run *fn*; record and print result. Returns True on success."""
    try:
        detail = fn() or ""
        _RESULTS.append((label, True, detail))
        suffix = f"  — {detail}" if detail else ""
        print(f"  ✅  {label}{suffix}")
        return True
    except Exception as exc:
        _RESULTS.append((label, False, str(exc)))
        print(f"  ❌  {label}  — {exc}")
        return False


# ── Individual checks ─────────────────────────────────────────────────────────

def check_config() -> str:
    """config.yaml is readable and all required keys are present."""
    from config_loader import get_config
    cfg = get_config()

    missing = [k for k in _REQUIRED_CONFIG_KEYS if not cfg.get(k)]
    if missing:
        raise RuntimeError(f"Missing required keys: {', '.join(missing)}")

    # Sanity-check key formats
    api_key = cfg.get("anthropic_api_key", "")
    if not api_key.startswith("sk-ant-"):
        raise RuntimeError(
            f"anthropic_api_key looks wrong (got: {api_key[:12]}…)"
        )

    return f"{len(cfg)} keys loaded"


def check_typing_log_dir() -> str:
    """Typing log directory (~/.typing-log) exists."""
    from config_loader import get_config
    cfg = get_config()
    d = pathlib.Path(cfg.get("typing_log_dir", "~/.typing-log")).expanduser()
    if not d.exists():
        raise RuntimeError(
            f"{d} does not exist. "
            "Is the typing daemon running? See daemon/typing-daemon."
        )
    files = list(d.glob("*.json"))
    return f"{d}  ({len(files)} log file(s))"


def check_plans_dir() -> str:
    """Plans dir (~/.daily-agent/plans) is writable."""
    from config_loader import get_config
    cfg = get_config()
    d = pathlib.Path(cfg.get("plans_dir", "~/.daily-agent/plans")).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    # Write + delete a sentinel file to verify write access
    sentinel = d / ".health_check_sentinel"
    sentinel.write_text("ok")
    sentinel.unlink()
    return str(d)


def check_activitywatch() -> str:
    """ActivityWatch REST API is reachable on localhost:5600."""
    import requests
    from config_loader import get_config
    cfg = get_config()
    host = cfg.get("activitywatch_host", "http://localhost:5600")
    url  = f"{host}/api/0/info"
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    version = data.get("version", "?")
    return f"{host}  (AW {version})"


def check_notion() -> str:
    """Notion API is reachable and the integration has access."""
    from config_loader import get_config
    cfg = get_config()
    import requests
    headers = {
        "Authorization": f"Bearer {cfg['notion_api_key']}",
        "Notion-Version": "2022-06-28",
    }
    # /v1/users/me is the lightest endpoint
    resp = requests.get("https://api.notion.com/v1/users/me",
                        headers=headers, timeout=10)
    if resp.status_code == 401:
        raise RuntimeError("Invalid Notion API key (401 Unauthorized)")
    resp.raise_for_status()
    name = resp.json().get("name") or resp.json().get("bot", {}).get("owner", {}).get("user", {}).get("name", "?")
    return f"authenticated as '{name}'"


def check_notion_pages() -> str:
    """Notion meetings DB and context page IDs are accessible."""
    from config_loader import get_config
    cfg = get_config()
    import requests

    headers = {
        "Authorization": f"Bearer {cfg['notion_api_key']}",
        "Notion-Version": "2022-06-28",
    }

    errors: list[str] = []

    # Check meetings database
    db_id = cfg.get("notion_meetings_db_id", "")
    if db_id:
        r = requests.get(f"https://api.notion.com/v1/databases/{db_id}",
                         headers=headers, timeout=10)
        if r.status_code == 404:
            errors.append(f"meetings DB {db_id[:8]}… not found (404)")
        elif r.status_code == 403:
            errors.append(f"meetings DB {db_id[:8]}… not shared with integration")
        elif not r.ok:
            errors.append(f"meetings DB error {r.status_code}")

    # Check context page
    page_id = cfg.get("notion_context_page_id", "")
    if page_id:
        r = requests.get(f"https://api.notion.com/v1/pages/{page_id}",
                         headers=headers, timeout=10)
        if r.status_code == 404:
            errors.append(f"context page {page_id[:8]}… not found (404)")
        elif r.status_code == 403:
            errors.append(f"context page {page_id[:8]}… not shared with integration")
        elif not r.ok:
            errors.append(f"context page error {r.status_code}")

    if errors:
        raise RuntimeError("; ".join(errors))

    return f"meetings DB + context page both accessible"


def check_telegram() -> str:
    """Telegram bot token is valid and the bot is reachable."""
    import requests
    from config_loader import get_config
    cfg = get_config()
    token   = cfg.get("telegram_bot_token", "")
    chat_id = cfg.get("telegram_chat_id", "")
    if not token:
        raise RuntimeError("telegram_bot_token is empty")

    url  = f"https://api.telegram.org/bot{token}/getMe"
    resp = requests.get(url, timeout=10)
    if resp.status_code == 401:
        raise RuntimeError("Invalid bot token (401 Unauthorized)")
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"getMe returned ok=false: {data}")

    bot_name = data["result"].get("username", "?")
    return f"@{bot_name}  (chat_id={chat_id})"


def check_anthropic_key() -> str:
    """Anthropic API key format is valid (does not make an API call)."""
    from config_loader import get_config
    cfg = get_config()
    key = cfg.get("anthropic_api_key", "")
    if not key:
        raise RuntimeError("anthropic_api_key is empty")
    if not key.startswith("sk-ant-"):
        raise RuntimeError(
            f"Key doesn't look like a valid Anthropic key "
            f"(expected 'sk-ant-…', got '{key[:12]}…')"
        )
    model = cfg.get("anthropic_model", "")
    return f"key OK  (model: {model})"


# ── Runner ────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Daily Agent health check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--skip-notion", action="store_true",
        help="Skip Notion connectivity checks",
    )
    parser.add_argument(
        "--skip-activitywatch", action="store_true",
        help="Skip ActivityWatch check (if AW isn't running)",
    )
    parser.add_argument(
        "--skip-telegram", action="store_true",
        help="Skip Telegram check",
    )
    args = parser.parse_args()

    print("\nDaily Agent — health check\n")
    t0 = time.monotonic()

    checks = [
        ("Config (config.yaml)",            check_config),
        ("Typing log dir",                  check_typing_log_dir),
        ("Plans dir (writable)",            check_plans_dir),
        ("Anthropic API key",               check_anthropic_key),
    ]
    if not args.skip_activitywatch:
        checks.append(("ActivityWatch",     check_activitywatch))
    if not args.skip_notion:
        checks.append(("Notion API",        check_notion))
        checks.append(("Notion pages/DBs",  check_notion_pages))
    if not args.skip_telegram:
        checks.append(("Telegram bot",      check_telegram))

    for label, fn in checks:
        _check(label, fn)

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    failed = sum(1 for _, ok, _ in _RESULTS if not ok)
    elapsed = time.monotonic() - t0

    print(f"\n{'─' * 50}")
    if failed == 0:
        print(f"  ✅  All {passed} checks passed  ({elapsed:.1f}s)")
    else:
        print(f"  {passed} passed  /  {failed} failed  ({elapsed:.1f}s)")
        print()
        print("  Failed checks:")
        for label, ok, detail in _RESULTS:
            if not ok:
                print(f"    ✗  {label}: {detail}")
        print()
        print("  Fix the issues above, then re-run `python health_check.py`")
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
