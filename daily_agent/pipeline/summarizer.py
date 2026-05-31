"""
Daily summarizer — two-stage pipeline.

Stage 1A  presummary_cursor_session / presummary_all_cursor
          Cheap haiku call per Cursor session → 3-5 sentence condensed summary.

Stage 1B  build_timeline
          Merges AW raw events + typing entries + cursor pre-summaries into a
          single sorted, budget-constrained chronological timeline.

Stage 2   summarize
          Builds the final prompt from timeline + meetings + context,
          calls the main Claude model, parses + validates JSON.

Also exposes parse_plan_edit for the Telegram plan-edit webhook.

CLI
---
  python pipeline/summarizer.py --test               # full end-to-end from fixture
  python pipeline/summarizer.py --test --stage1-only # Stage 1A+1B only (no API call)
  python pipeline/summarizer.py --test --show-prompt # print final prompt and exit
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys
import textwrap

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import anthropic

from config_loader import get_config
from utils.logger import get_logger

log = get_logger("summarizer")

# ── bundle_id → AW app-name mapping (for typing attachment) ──────────────────

_BUNDLE_TO_AW_APP: dict[str, str] = {
    "com.google.Chrome":               "Google Chrome",
    "com.apple.Safari":                "Safari",
    "org.mozilla.firefox":             "Firefox",
    "company.thebrowser.Browser":      "Arc",
    "com.todesktop.230313mzl4w4u92":   "Cursor",
    "com.microsoft.VSCode":            "Code",
    "io.claude.app":                   "Claude",
    "com.notion.mac":                  "Notion",
    "com.apple.Notes":                 "Notes",
    "com.microsoft.Word":              "Microsoft Word",
    "com.microsoft.Powerpoint":        "Microsoft PowerPoint",
    "com.tinyspeck.slackmacgap":       "Slack",
    "com.apple.mail":                  "Mail",
    "com.apple.MobileSMS":             "Messages",
    "zoom.us":                         "Zoom",
    "com.googlecode.iterm2":           "iTerm2",
    "com.apple.Terminal":              "Terminal",
}


def _bundle_matches_app(bundle_id: str, app_name: str) -> bool:
    """
    Return True if *bundle_id* is consistent with *app_name*.
    Unknown bundle_ids use a loose substring match; missing bundle_id always passes.
    """
    if not bundle_id:
        return True
    mapped = _BUNDLE_TO_AW_APP.get(bundle_id)
    if mapped is not None:
        return mapped.lower() == app_name.lower()
    # Unknown bundle: check if any meaningful part of the bundle appears in app name
    app_lower = app_name.lower()
    for part in bundle_id.lower().split("."):
        if len(part) > 3 and part in app_lower:
            return True
    return False


# ── low-level helpers ─────────────────────────────────────────────────────────

def _parse_iso(iso_str: str) -> datetime.datetime:
    dt = datetime.datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _epoch(iso_str: str) -> float:
    """ISO timestamp → Unix epoch seconds."""
    return _parse_iso(iso_str).timestamp()


def _local_hhmm(iso_str: str) -> str:
    """ISO timestamp → local HH:MM string (uses configured timezone)."""
    if not iso_str:
        return "??:??"
    try:
        dt = _parse_iso(iso_str)
        import pytz
        cfg = get_config()
        tz = pytz.timezone(cfg.get("timezone", "Asia/Jerusalem"))
        return dt.astimezone(tz).strftime("%H:%M")
    except Exception:
        try:
            return _parse_iso(iso_str).strftime("%H:%M")
        except Exception:
            return "??:??"


# ── Claude API helper ─────────────────────────────────────────────────────────

def _call_claude(
    system: str,
    user: str,
    max_tokens: int,
    model: str,
    temperature: float = 0,
) -> tuple[str, int, int]:
    """
    Call the Anthropic Messages API.

    Returns (response_text, input_tokens, output_tokens).
    Raises anthropic.APIError on failure.
    """
    cfg = get_config()
    client = anthropic.Anthropic(api_key=cfg["anthropic_api_key"])
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = msg.content[0].text
    return text, msg.usage.input_tokens, msg.usage.output_tokens


def _extract_json(text: str) -> dict | list:
    """
    Extract JSON from a Claude response.
    Handles bare JSON and ```json...``` / ```...``` code fences.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end]).strip()
    return json.loads(text)


# ── Stage 1A: Cursor pre-summarizer ──────────────────────────────────────────

_CURSOR_PRESUMMARY_SYSTEM = (
    "You summarize coding sessions. Extract only what matters for a daily "
    "productivity review. Be specific about what was built or fixed. "
    "Ignore: code listings, error messages, repeated attempts, file contents "
    "pasted as context."
)


def _format_turns_for_presummary(user_turns: list[str], max_chars: int = 3000) -> str:
    """Number the turns; truncate with a count message if over max_chars."""
    lines: list[str] = []
    total = 0
    for i, turn in enumerate(user_turns, 1):
        line = f"{i}. {turn.strip()}\n"
        if total + len(line) > max_chars:
            remaining = len(user_turns) - i + 1
            lines.append(f"[... {remaining} more turn(s) truncated]\n")
            break
        lines.append(line)
        total += len(line)
    return "".join(lines).rstrip()


def presummary_cursor_session(session: dict) -> dict:
    """
    Run a cheap haiku call to condense one Cursor session into 3-5 sentences.

    Input  – one session dict from collect_cursor:
               {session_id, workspace, started_at, user_turns, turn_count}
    Output – {session_id, started_at, workspace, summary, token_count}
    Falls back to the main model if the haiku call fails.
    """
    cfg = get_config()
    haiku_model: str = cfg.get(
        "anthropic_cursor_presummary_model", "claude-haiku-4-5-20251001"
    )
    main_model: str = cfg.get("anthropic_model", "claude-sonnet-4-6")

    session_id = session.get("session_id", "?")
    workspace = session.get("workspace", "unknown")
    started_at = session.get("started_at", "")
    user_turns = session.get("user_turns", [])
    turn_count = session.get("turn_count", len(user_turns))

    turns_text = _format_turns_for_presummary(user_turns)

    user_msg = (
        f"Workspace: {workspace}\n"
        f"Session started: {started_at}\n"
        f"User turns ({turn_count} total):\n"
        f"{turns_text}\n\n"
        "Summarize:\n"
        "- What problem or task was being worked on (one sentence)\n"
        "- The approach taken\n"
        "- Whether it was resolved or left open\n"
        "- Any key decisions, insights, or blockers\n"
        "Output: 3-5 sentences, plain text, no bullet points."
    )

    token_count = 0
    for model in (haiku_model, main_model):
        try:
            text, in_tok, out_tok = _call_claude(
                _CURSOR_PRESUMMARY_SYSTEM, user_msg,
                max_tokens=200, model=model, temperature=0,
            )
            token_count = in_tok + out_tok
            log.info(
                "Cursor pre-summary %s: model=%s tokens=%d+%d",
                session_id[:16], model, in_tok, out_tok,
            )
            return {
                "session_id": session_id,
                "started_at": started_at,
                "workspace": workspace,
                "summary": text.strip(),
                "token_count": token_count,
            }
        except anthropic.APIError as exc:
            if model == haiku_model:
                log.warning(
                    "Haiku pre-summary failed for %s (%s) — retrying with %s",
                    session_id[:16], exc, main_model,
                )
            else:
                log.error("Pre-summary failed for %s: %s", session_id[:16], exc)
                break
        except Exception as exc:
            log.error("Unexpected pre-summary error for %s: %s", session_id[:16], exc)
            break

    return {
        "session_id": session_id,
        "started_at": started_at,
        "workspace": workspace,
        "summary": "[summarization failed]",
        "token_count": 0,
    }


def presummary_all_cursor(sessions: list[dict]) -> list[dict]:
    """
    Run presummary_cursor_session() for each session sequentially.
    Failures are logged and replaced with a placeholder summary.
    Returns total Stage-1A token count as the last element's sentinel
    (callers sum token_count from each entry).
    """
    results: list[dict] = []
    for session in sessions:
        try:
            result = presummary_cursor_session(session)
        except Exception as exc:
            sid = session.get("session_id", "?")
            log.warning("presummary_cursor_session raised for %s: %s", sid, exc)
            result = {
                "session_id": session.get("session_id", "?"),
                "started_at": session.get("started_at", ""),
                "workspace": session.get("workspace", "unknown"),
                "summary": "[summarization failed]",
                "token_count": 0,
            }
        results.append(result)

    total_tokens = sum(r.get("token_count", 0) for r in results)
    log.info("Stage 1A complete: %d sessions, %d total tokens", len(results), total_tokens)
    return results


# ── Stage 1B: Timeline builder ────────────────────────────────────────────────

def _merge_into_segments(raw_events: list[dict], min_secs: float) -> list[dict]:
    """
    Merge consecutive same-app events with gap < 60 s, then drop segments
    shorter than *min_secs*.

    Returns list of internal segment dicts:
      {app, title, domain, start_iso, end_iso, duration_seconds, _raw_count}
    """
    if not raw_events:
        return []

    sorted_evs = sorted(raw_events, key=lambda e: e["start_iso"])
    segments: list[dict] = []

    for ev in sorted_evs:
        if not segments or segments[-1]["app"] != ev["app"]:
            segments.append({
                "app": ev["app"],
                "title": ev["title"],
                "domain": ev.get("domain"),
                "start_iso": ev["start_iso"],
                "end_iso": ev["end_iso"],
                "duration_seconds": ev["duration_seconds"],
                "_raw_count": 1,
            })
            continue

        last = segments[-1]
        gap = _epoch(ev["start_iso"]) - _epoch(last["end_iso"])
        if gap < 60:
            # Absorb: extend end, accumulate duration (including the gap itself)
            last["end_iso"] = ev["end_iso"]
            last["duration_seconds"] += ev["duration_seconds"] + max(0.0, gap)
            last["_raw_count"] += 1
            # Promote domain if first event had none
            if ev.get("domain") and not last["domain"]:
                last["domain"] = ev["domain"]
        else:
            segments.append({
                "app": ev["app"],
                "title": ev["title"],
                "domain": ev.get("domain"),
                "start_iso": ev["start_iso"],
                "end_iso": ev["end_iso"],
                "duration_seconds": ev["duration_seconds"],
                "_raw_count": 1,
            })

    kept = [s for s in segments if s["duration_seconds"] >= min_secs]
    dropped = len(segments) - len(kept)
    if dropped:
        log.debug("Timeline: dropped %d sub-%ds segments", dropped, int(min_secs))
    return kept


def _attach_typing_to_segments(
    segments: list[dict],
    typing_entries: list[dict],
) -> None:
    """
    Mutate segments in place: add '_typing_entries' (full entry dicts)
    and 'typing' (list of text strings for full/domain-mode entries).

    Matching rule: entry.timestamp in [seg.start-30s, seg.end+30s]
                   AND entry.bundle_id consistent with seg.app.
    """
    for seg in segments:
        try:
            seg_s = _epoch(seg["start_iso"]) - 30.0
            seg_e = _epoch(seg["end_iso"]) + 30.0
        except Exception:
            seg["_typing_entries"] = []
            seg["typing"] = []
            continue

        matched: list[dict] = []
        for entry in typing_entries:
            ts_str = entry.get("timestamp", "")
            if not ts_str:
                continue
            try:
                ts = _epoch(ts_str)
            except Exception:
                continue
            if not (seg_s <= ts <= seg_e):
                continue
            bid = entry.get("bundle_id", "")
            if not _bundle_matches_app(bid, seg["app"]):
                continue
            matched.append(entry)

        seg["_typing_entries"] = matched
        seg["typing"] = [
            e.get("text", "").strip()
            for e in matched
            if e.get("_mode") in ("full", "domain") and e.get("text", "").strip()
        ]


def _attach_cursor_presummaries(
    segments: list[dict],
    cursor_presummaries: list[dict],
) -> list[dict]:
    """
    Attach cursor presummaries to matching segments (by timestamp overlap).
    Creates a synthetic segment if no matching segment exists.

    Returns the (possibly extended) segments list.
    """
    for pre in cursor_presummaries:
        started_at = pre.get("started_at", "")
        if not started_at:
            continue
        try:
            start_ep = _epoch(started_at)
        except Exception:
            continue

        matched_seg = None
        for seg in segments:
            try:
                if _epoch(seg["start_iso"]) <= start_ep <= _epoch(seg["end_iso"]):
                    matched_seg = seg
                    break
            except Exception:
                continue

        if matched_seg is not None:
            matched_seg["cursor_summary"] = pre.get("summary", "")
        else:
            log.debug(
                "No AW segment for Cursor session %s — creating synthetic",
                pre.get("session_id", "?")[:16],
            )
            segments.append({
                "app": "Cursor",
                "title": f"workspace: {pre.get('workspace', 'unknown')}",
                "domain": None,
                "start_iso": started_at,
                "end_iso": started_at,
                "duration_seconds": 0,
                "_raw_count": 0,
                "_typing_entries": [],
                "typing": [],
                "cursor_summary": pre.get("summary", ""),
                "synthetic": True,
            })

    return segments


def _determine_capture_mode(seg: dict) -> str:
    if seg.get("cursor_summary"):
        return "full"
    modes = [e.get("_mode", "charcount") for e in seg.get("_typing_entries", [])]
    if any(m in ("full", "domain") for m in modes):
        return "full"
    if "summary" in modes:
        return "summary"
    return "charcount"


def build_timeline(
    typing_entries: list[dict],
    activitywatch: dict,
    cursor_presummaries: list[dict],
) -> list[dict]:
    """
    Merge AW raw events, typing entries, and cursor pre-summaries into a
    single chronological timeline.

    Returns list of timeline entry dicts:
      { start, end, duration_minutes, app, domain, typing, cursor_summary,
        capture_mode, synthetic }
    """
    cfg = get_config()
    min_secs = cfg.get("min_segment_minutes", 3) * 60

    raw_events: list[dict] = activitywatch.get("raw_events", [])
    if not raw_events:
        log.warning(
            "build_timeline: activitywatch has no raw_events — "
            "only synthetic Cursor segments will appear"
        )

    # Step 1: merge into segments
    segments = _merge_into_segments(raw_events, min_secs)

    # Step 2: attach typing entries
    _attach_typing_to_segments(segments, typing_entries)

    # Step 3: attach cursor presummaries (may add synthetic segments)
    segments = _attach_cursor_presummaries(segments, cursor_presummaries)

    # Step 4: format output
    timeline: list[dict] = []
    for seg in sorted(segments, key=lambda s: s["start_iso"]):
        domain = seg.get("domain")
        app_label = f"{seg['app']}/{domain}" if domain else seg["app"]

        timeline.append({
            "start":            _local_hhmm(seg["start_iso"]),
            "end":              _local_hhmm(seg["end_iso"]),
            "duration_minutes": max(0, round(seg["duration_seconds"] / 60)),
            "app":              app_label,
            "domain":           domain,
            "typing":           seg.get("typing", []),
            "cursor_summary":   seg.get("cursor_summary"),
            "capture_mode":     _determine_capture_mode(seg),
            "synthetic":        seg.get("synthetic", False),
        })

    log.info("build_timeline: %d segments from %d raw events", len(timeline), len(raw_events))
    return timeline


# ── Stage 2: Main summarizer ───────────────────────────────────────────────────

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a personal productivity assistant with full access to everything the user
    actually did on their computer today. Your job is to:

    1. Write a concise, SEMANTIC daily summary — what was actually accomplished,
       not just which apps were open. Name real topics, decisions, and projects.
    2. Generate a prioritized plan for tomorrow based on today's output,
       unfinished work, and the user's stated goals.

    Rules:
    - Be direct and specific. If the user spent 40 minutes asking an AI about
      system architecture, write "Designed system architecture for X" — not "used Claude.ai".
    - Infer intent from context clues (window titles, text content, meeting topics).
    - For the plan, output 5–7 concrete, actionable tasks ordered by priority.
    - Do NOT mention raw app names or URLs in the summary — translate to meaning.
    - Output ONLY valid JSON matching the schema in the user message. No explanation.
""")

_OUTPUT_SCHEMA = textwrap.dedent("""\
    === OUTPUT SCHEMA ===
    Return ONLY valid JSON — no markdown fences, no explanation:
    {
      "summary": "3-5 paragraph narrative of what was actually accomplished today",
      "highlights": ["key accomplishment 1", "key accomplishment 2", "..."],
      "tomorrow_plan": [
        {"id": 1, "task": "...", "priority": "high|medium|low", "context": "why this task"},
        ...
      ],
      "time_breakdown": [
        {"app": "Chrome", "minutes": 120, "category": "research|coding|writing|meetings|admin|other"},
        ...
      ],
      "blockers": ["anything that seems stuck or unresolved"]
    }
""")

_PLAN_EDIT_SYSTEM = textwrap.dedent("""\
    You are a plan editor. Given a JSON plan and a plain-English edit request,
    return the updated plan as a JSON array. Same schema as input. No explanation.
    Output ONLY the JSON array.
""")


def _render_segment(seg: dict, typing_limit: int) -> str:
    lines: list[str] = []
    if seg.get("synthetic"):
        lines.append(f"[Cursor session — workspace: {seg['app'].replace('Cursor/', '')}]")
    else:
        lines.append(
            f"[{seg['start']}–{seg['end']}] {seg['app']} — {seg['duration_minutes']} min"
        )

    cursor_summary = seg.get("cursor_summary")
    typing = seg.get("typing", [])
    capture_mode = seg.get("capture_mode", "charcount")

    if cursor_summary:
        lines.append(f"  Coding session: {cursor_summary}")
    elif typing and capture_mode == "full":
        lines.append("  Typed:")
        for t in typing[:typing_limit]:
            lines.append(f"  • {t}")
    elif capture_mode in ("summary", "charcount"):
        lines.append("  [content not captured for this app]")
    else:
        lines.append("  [reading / browsing — no typed input]")

    return "\n".join(lines)


def _render_timeline_section(timeline: list[dict], max_timeline_tokens: int) -> str:
    """
    Render the chronological section, applying budget cuts if needed.

    Priority order for removal (never remove Cursor segments):
      1. charcount-mode non-Cursor segments
      2. Truncate typing to 3 entries per segment
      3. summary-mode segments
      4. Truncate to 2 entries (domain-filter segments already at 3)
    """
    cfg = get_config()
    max_typing = cfg.get("max_typing_per_segment", 6)
    max_chars = max_timeline_tokens * 4

    def _render_all(tl: list[dict], typing_limit: int) -> str:
        return "\n\n".join(_render_segment(s, typing_limit) for s in tl)

    full = _render_all(timeline, max_typing)
    if len(full) <= max_chars:
        return full

    # Cut 1: drop charcount-only, non-Cursor segments
    is_cursor = lambda s: "Cursor" in s["app"] or s.get("cursor_summary")
    reduced = [
        s for s in timeline
        if is_cursor(s) or s.get("capture_mode") != "charcount"
    ]
    dropped = len(timeline) - len(reduced)
    if dropped:
        log.warning("Timeline budget: dropped %d charcount segment(s)", dropped)
    text = _render_all(reduced, max_typing)
    if len(text) <= max_chars:
        return text

    # Cut 2: truncate typing to 3
    log.warning("Timeline budget: truncating typing lists to 3 entries")
    text = _render_all(reduced, 3)
    if len(text) <= max_chars:
        return text

    # Cut 3: drop summary-mode segments
    reduced2 = [
        s for s in reduced
        if is_cursor(s) or s.get("capture_mode") != "summary"
    ]
    dropped2 = len(reduced) - len(reduced2)
    if dropped2:
        log.warning("Timeline budget: dropped %d summary-mode segment(s)", dropped2)
    text = _render_all(reduced2, 3)
    if len(text) <= max_chars:
        return text

    # Cut 4: typing to 2
    log.warning("Timeline budget: truncating typing lists to 2 entries")
    text = _render_all(reduced2, 2)
    if len(text) <= max_chars:
        return text

    # Last resort: hard truncate
    log.warning(
        "Timeline budget: hard truncating to %d chars (was %d)", max_chars, len(text)
    )
    return text[:max_chars] + "\n[... timeline truncated for token budget ...]"


def _render_micro_section(micro_summaries: list[dict]) -> str:
    """Render micro-summaries as a compact text block for the prompt."""
    lines: list[str] = []
    for m in micro_summaries:
        ws = m.get("window_start", "")
        we = m.get("window_end", "")
        # e.g. "10:00–10:30"
        ws_hm = ws[11:16] if len(ws) >= 16 else ws[:5]
        we_hm = we[11:16] if len(we) >= 16 else we[:5]
        app   = m.get("app", "?")
        mins  = int(m.get("minutes", 0))
        summ  = m.get("summary", "")
        lines.append(f"[{ws_hm}–{we_hm}] {app} ({mins}m): {summ}")
    return "\n".join(lines)


def build_prompt(
    timeline: list[dict],
    meetings: list[dict],
    context: dict,
    date: datetime.date,
    micro_summaries: list[dict] | None = None,
) -> str:
    """
    Construct the user-turn prompt for the main summarizer call.

    Parameters
    ----------
    timeline        : output of build_timeline()
    meetings        : list from collect_notion_meetings.get_date()
    context         : {general: str, today: {plan: str, actual: str} | None}
    date            : the day being summarized
    micro_summaries : optional list of 30-min window summaries; when provided
                      these replace the detailed typing analysis (token reduction).
    """
    cfg = get_config()
    max_context_chars   = cfg.get("max_context_tokens", 600) * 4
    max_meeting_chars   = cfg.get("max_meeting_tokens", 800) * 4
    max_timeline_tokens = cfg.get("max_timeline_tokens", 3000)

    day_of_week = date.strftime("%A")

    # Context section
    general_ctx = (context.get("general") or "")[:max_context_chars]
    today_ctx   = context.get("today") or {}
    today_plan  = today_ctx.get("plan", "") if today_ctx else ""

    # Meetings section
    meeting_lines: list[str] = []
    for m in meetings:
        time_str = m.get("time", "")
        title    = m.get("title", "Untitled")
        summary  = (m.get("summary") or "").strip()
        header   = f"[{time_str}] {title}" if time_str else title
        meeting_lines.append(f"\n{header}")
        if summary:
            meeting_lines.append(summary[:500])
    meetings_text = "".join(meeting_lines).strip()
    if len(meetings_text) > max_meeting_chars:
        meetings_text = meetings_text[:max_meeting_chars] + "\n[... truncated ...]"
    if not meetings_text:
        meetings_text = "No conversations logged today."

    # Day section: use micro-summaries (token-saving) or full timeline
    if micro_summaries:
        micro_text = _render_micro_section(micro_summaries)
        # Keep the timeline for time-allocation context only (strip typing to save tokens)
        light_tl  = [{**s, "typing": []} for s in timeline]
        tl_text   = _render_timeline_section(light_tl, max_timeline_tokens // 2)
        day_section = (
            "=== ACTIVITY SUMMARIES (30-MIN WINDOWS) ===\n"
            f"{micro_text}\n"
            "\n"
            "=== TIME ALLOCATION (from activity tracking) ===\n"
            f"{tl_text}"
        )
    else:
        timeline_text = _render_timeline_section(timeline, max_timeline_tokens)
        day_section   = (
            "=== YOUR DAY — CHRONOLOGICAL ===\n"
            f"{timeline_text}"
        )

    return (
        f"TODAY'S DATE: {date} ({day_of_week})\n"
        "\n"
        "=== YOUR CONTEXT ===\n"
        f"{general_ctx or '(no general context provided)'}\n"
        "\n"
        "=== TODAY'S PLANNED TASKS ===\n"
        f"{today_plan or 'No plan was set for today.'}\n"
        "\n"
        f"{day_section}\n"
        "\n"
        "=== CONVERSATIONS TODAY ===\n"
        f"{meetings_text}\n"
        "\n"
        f"{_OUTPUT_SCHEMA}"
    )


def summarize(
    typing_entries: list[dict],
    activitywatch: dict,
    cursor_sessions: list[dict],
    meetings: list[dict],
    context: dict,
    date: datetime.date,
) -> dict:
    """
    Run the full two-stage pipeline and return a structured result dict.

    Stage 1A: pre-summarize each Cursor session (haiku model)
    Stage 1B: build chronological timeline
    Stage 2:  call main model, parse JSON

    On hard failure returns {"error": str, ...empty fields...}.
    On JSON parse failure raises ValueError.
    """
    cfg = get_config()
    model: str = cfg.get("anthropic_model", "claude-sonnet-4-6")
    max_tokens: int = cfg.get("anthropic_max_tokens", 1500)

    stage1a_tokens = 0

    # ── Stage 1A ──────────────────────────────────────────────────────────
    log.info("=== Stage 1A: Cursor pre-summarizer (%d sessions) ===", len(cursor_sessions))
    cursor_presummaries = presummary_all_cursor(cursor_sessions)
    stage1a_tokens = sum(p.get("token_count", 0) for p in cursor_presummaries)

    # ── Stage 1B ──────────────────────────────────────────────────────────
    log.info("=== Stage 1B: Build timeline ===")
    timeline = build_timeline(typing_entries, activitywatch, cursor_presummaries)

    # ── Micro-summaries (token reduction) ─────────────────────────────────
    # If 30-minute window summaries exist for today, use them instead of raw
    # typing entries — cuts input cost from ~5 000 tokens to ~2 000 tokens.
    micro: list[dict] = []
    try:
        from pipeline.micro_summarizer import get_micro_summaries
        micro = get_micro_summaries(date)
        if micro:
            log.info(
                "Micro-summaries loaded: %d entries for %s — using condensed prompt",
                len(micro), date,
            )
    except Exception as exc:
        log.debug("micro_summarizer unavailable (using full pipeline): %s", exc)

    # ── Stage 2 ───────────────────────────────────────────────────────────
    log.info("=== Stage 2: Main summarizer (model=%s) ===", model)
    prompt = build_prompt(timeline, meetings, context, date, micro_summaries=micro or None)
    prompt_tokens_approx = len(prompt) // 4
    log.info(
        "Prompt: ~%d tokens  Stage1A: %d tokens  max_output: %d",
        prompt_tokens_approx, stage1a_tokens, max_tokens,
    )

    try:
        raw, in_tok, out_tok = _call_claude(
            _SYSTEM_PROMPT, prompt, max_tokens, model, temperature=0
        )
    except anthropic.APIError as exc:
        log.error("Claude API error: %s", exc)
        return {
            "error": str(exc),
            "summary": "", "highlights": [],
            "tomorrow_plan": [], "time_breakdown": [], "blockers": [],
        }
    except Exception as exc:
        log.error("Unexpected error calling Claude: %s", exc)
        return {
            "error": str(exc),
            "summary": "", "highlights": [],
            "tomorrow_plan": [], "time_breakdown": [], "blockers": [],
        }

    log.info(
        "Stage 2 complete: %d input tokens, %d output tokens  "
        "(Stage1A: %d)  total: %d",
        in_tok, out_tok, stage1a_tokens, in_tok + out_tok + stage1a_tokens,
    )
    log.debug("Raw response (first 300 chars): %s", raw[:300])

    try:
        result = _extract_json(raw)
    except json.JSONDecodeError as exc:
        log.error("JSON parse failed: %s\nRaw: %s", exc, raw[:600])
        raise ValueError(
            f"Claude returned non-JSON response: {exc}\n\nRaw (first 400 chars):\n{raw[:400]}"
        ) from exc

    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object, got {type(result)}")

    # Normalise key aliases
    if "plan" in result and "tomorrow_plan" not in result:
        result["tomorrow_plan"] = result.pop("plan")

    # Ensure all expected keys present
    result.setdefault("summary", "")
    result.setdefault("highlights", [])
    result.setdefault("tomorrow_plan", [])
    result.setdefault("time_breakdown", [])
    result.setdefault("blockers", [])

    log.info(
        "Summarize done: %d plan tasks, %d highlights, %d blockers",
        len(result["tomorrow_plan"]),
        len(result["highlights"]),
        len(result["blockers"]),
    )
    return result


# ── Plan edit ─────────────────────────────────────────────────────────────────

def parse_plan_edit(current_plan: list[dict], edit_request: str) -> list[dict]:
    """
    Apply *edit_request* (plain English) to *current_plan* via a small Claude call.

    Returns the updated plan list (same schema as tomorrow_plan).
    Raises RuntimeError on API or parse failure.
    """
    cfg = get_config()
    model: str = cfg.get(
        "anthropic_cursor_presummary_model",
        cfg.get("anthropic_model", "claude-haiku-4-5-20251001"),
    )
    max_tokens: int = cfg.get("anthropic_cursor_presummary_max_tokens", 400)

    plan_json = json.dumps(current_plan, ensure_ascii=False)
    user_msg = (
        f"Current plan:\n{plan_json}\n\n"
        f'Edit request: "{edit_request}"\n\n'
        "Return the updated plan as a JSON array. Same schema. No explanation."
    )

    try:
        raw, _, _ = _call_claude(_PLAN_EDIT_SYSTEM, user_msg, max_tokens, model)
    except anthropic.APIError as exc:
        raise RuntimeError(f"Claude API error during plan edit: {exc}") from exc

    try:
        updated = _extract_json(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse updated plan JSON: {exc}\nRaw: {raw[:300]}"
        ) from exc

    if not isinstance(updated, list):
        raise RuntimeError(f"Expected a JSON array from plan edit, got: {type(updated)}")

    log.info("Plan edit applied: %d tasks", len(updated))
    return updated


# ── CLI ───────────────────────────────────────────────────────────────────────

def _load_fixture() -> dict:
    """Load the test fixture from tests/fixture_day.json."""
    fixture_path = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixture_day.json"
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    # Parse date string → datetime.date
    raw["date"] = datetime.date.fromisoformat(raw["date"])
    return raw


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Summarizer pipeline test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run end-to-end using tests/fixture_day.json",
    )
    parser.add_argument(
        "--stage1-only", action="store_true",
        help="Run Stage 1A + 1B only (no main Claude call)",
    )
    parser.add_argument(
        "--show-prompt", action="store_true",
        help="Print the final Stage-2 prompt and exit (no Claude call)",
    )
    parser.add_argument(
        "--out", metavar="FILE",
        help="Write JSON result to file",
    )
    args = parser.parse_args()

    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    console = Console()

    if args.test:
        try:
            fixture = _load_fixture()
        except FileNotFoundError as exc:
            console.print(f"[red]{exc}[/]")
            sys.exit(1)

        date = fixture["date"]
        typing_entries = fixture.get("typing", [])
        activitywatch = fixture.get("activitywatch", {})
        cursor_sessions = fixture.get("cursor_sessions", [])
        meetings = fixture.get("meetings", [])
        context = fixture.get("context", {})

        console.print(f"\n[bold cyan]Fixture date:[/] {date}")
        console.print(
            f"  typing={len(typing_entries)}  "
            f"raw_events={len(activitywatch.get('raw_events', []))}  "
            f"cursor_sessions={len(cursor_sessions)}  "
            f"meetings={len(meetings)}"
        )

        # Stage 1A
        console.print("\n[bold]Stage 1A — Cursor pre-summarizer[/]")
        presummaries = presummary_all_cursor(cursor_sessions)
        for p in presummaries:
            console.print(Panel(
                p["summary"],
                title=f"[cyan]{p['workspace']}[/]  {p['started_at'][:16]}  "
                      f"[dim](tokens: {p['token_count']})[/]",
                expand=False,
            ))

        # Stage 1B
        console.print("\n[bold]Stage 1B — Timeline[/]")
        timeline = build_timeline(typing_entries, activitywatch, presummaries)
        t = Table(show_header=True, header_style="bold magenta")
        t.add_column("Time", style="cyan", no_wrap=True)
        t.add_column("App")
        t.add_column("Min", justify="right")
        t.add_column("Mode")
        t.add_column("Typing / Cursor summary", overflow="fold")
        for seg in timeline:
            time_label = f"{seg['start']}–{seg['end']}"
            if seg.get("synthetic"):
                time_label = "[synthetic]"
            content = ""
            if seg.get("cursor_summary"):
                content = seg["cursor_summary"][:80]
            elif seg.get("typing"):
                content = seg["typing"][0][:80]
            t.add_row(
                time_label,
                seg["app"],
                str(seg["duration_minutes"]),
                seg["capture_mode"],
                content,
            )
        console.print(t)

        if args.stage1_only:
            console.print("\n[dim]--stage1-only: stopping before Stage 2.[/]")
            return

        # Build prompt
        prompt = build_prompt(timeline, meetings, context, date)
        console.print(
            f"\n[dim]Prompt: {len(prompt)} chars (~{len(prompt)//4} tokens)[/]"
        )

        if args.show_prompt:
            console.print(Panel(prompt, title="[bold]Final prompt[/]", expand=False))
            return

        # Stage 2
        console.print("\n[bold]Stage 2 — Main summarizer[/]")
        result = summarize(
            typing_entries=typing_entries,
            activitywatch=activitywatch,
            cursor_sessions=cursor_sessions,
            meetings=meetings,
            context=context,
            date=date,
        )

        if "error" in result:
            console.print(f"[red]Error: {result['error']}[/]")
            sys.exit(1)

        console.print("\n[bold green]Summary:[/]")
        console.print(result.get("summary", ""))

        console.print("\n[bold]Highlights:[/]")
        for h in result.get("highlights", []):
            console.print(f"  • {h}")

        console.print("\n[bold]Tomorrow's plan:[/]")
        for task in result.get("tomorrow_plan", []):
            pri = task.get("priority", "?").upper()
            console.print(
                f"  [{pri}] {task.get('task', '')}  — {task.get('context', '')}"
            )

        if result.get("blockers"):
            console.print("\n[bold yellow]Blockers:[/]")
            for b in result["blockers"]:
                console.print(f"  ⚠ {b}")

        if args.out:
            pathlib.Path(args.out).write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            console.print(f"\n[dim]Result written to {args.out}[/]")

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
