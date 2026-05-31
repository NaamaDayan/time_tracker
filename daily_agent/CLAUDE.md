# Daily Agent — Architecture & Build Guide

## What This System Does

A personal productivity agent that runs on your Mac, silently collects what you
actually did today (typed text, active apps, meeting transcripts, Cursor sessions),
synthesizes a semantic daily summary + next-day plan, and delivers it to Telegram at
end of day. You reply to edit the plan. Everything runs locally except one Claude API
call per day.

---

## Project Structure

```
daily-agent/
├── CLAUDE.md                        ← you are here
├── README.md
│
├── daemon/                          ← ALREADY BUILT (do not modify)
│   └── typing-daemon                ← macOS Swift/Python daemon
│       Writes: ~/.typing-log/YYYY-MM-DD.json
│       Schema: [{timestamp, app, bundle_id, window_title, text}]
│
├── collectors/                      ← data collection scripts (build these)
│   ├── collect_typing.py            ← reads ~/.typing-log/today.json, filters + dedupes
│   ├── collect_activitywatch.py     ← queries ActivityWatch REST API on localhost:5600
│   ├── collect_cursor.py            ← reads Cursor SQLite at ~/.cursor/User/workspaceStorage/
│   └── collect_notion_meetings.py   ← queries Notion API for today's meeting summaries
│
├── pipeline/                        ← the daily processing pipeline
│   ├── run_daily.py                 ← main entry point, called by cron/OpenClaw at 20:00
│   ├── summarizer.py                ← Claude API call, constructs prompt, parses response
│   ├── micro_summarizer.py          ← optional: runs every 30min during the day
│   └── plan_store.py                ← persists + updates tomorrow's plan (JSON file)
│
├── delivery/                        ← Telegram integration
│   ├── telegram_send.py             ← sends formatted message via Bot API
│   └── telegram_webhook.py          ← receives replies, parses plan edits, confirms
│
├── context/                         ← user-controlled context (pulled from Notion)
│   └── fetch_context.py             ← reads the "Agent Context" Notion page
│
├── claw.md                          ← OpenClaw skill definition (cron + Telegram wiring)
│
├── config.yaml                      ← all configuration (API keys, paths, Notion IDs)
├── requirements.txt
└── logs/
    └── agent-YYYY-MM-DD.log
```

---

## Data Sources & Schemas

### 1. Typing Daemon Output (ALREADY EXISTS — READ ONLY)
**Location:** `~/.typing-log/YYYY-MM-DD.json`

```json
[
  {
    "timestamp": "2026-05-29T14:32:11Z",
    "app": "Google Chrome",
    "bundle_id": "com.google.Chrome",
    "window_title": "Claude - New conversation",
    "text": "what is the best architecture for a daily summarization agent"
  }
]
```

**Key bundle IDs to watch:**
- `com.google.Chrome` / `com.apple.Safari` — browser (check window_title for domain)
- `com.todesktop.230313mzl4w4u92` — Cursor IDE
- `io.claude.app` — Claude desktop (if used)
- `com.apple.Notes` — Notes.app
- `com.microsoft.Word` / `com.microsoft.Powerpoint`
- `com.notion.mac` — Notion desktop

### 2. ActivityWatch (time-tracking)
**Source:** `http://localhost:5600/api/0/buckets/`

Relevant buckets:
- `aw-watcher-window_<hostname>` — active app + window title, 1-second resolution
- `aw-watcher-web-chrome` — active Chrome tab URL + title
- `aw-watcher-afk_<hostname>` — idle/active detection

Query endpoint: `GET /api/0/query/`

```python
# Example: get today's app time
{
  "timeperiods": ["2026-05-29T00:00:00/2026-05-30T00:00:00"],
  "query": [
    "events = query_bucket(find_bucket('aw-watcher-window_'));",
    "events = filter_keyvals(events, 'status', ['not-afk']);",
    "events = merge_events_by_keys(events, ['app', 'title']);",
    "RETURN = sort_by_duration(events);"
  ]
}
```

Returns array of `{app, title, duration_seconds}`.

### 3. Cursor IDE Sessions
**Location:** `~/.cursor/User/workspaceStorage/*/`

Two SQLite DBs to check per workspace:
- `backup.db` → table `composer.composerData` (JSON blob) → current sessions
- `state.vscdb` → table `ItemTable` where key = `'workbench.panel.aichat.view.aichat.chatdata'`

Use `cursor-history` CLI if installed (`npm install -g cursor-history`):
```bash
cursor-history export --since today --format json -o /tmp/cursor-today.json
```

Or query directly:
```python
import sqlite3, json, glob, pathlib
from datetime import date

workspaces = pathlib.Path.home() / ".cursor/User/workspaceStorage"
for db_path in workspaces.glob("*/backup.db"):
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT value FROM ItemTable WHERE key = 'composer.composerData'").fetchall()
    # parse JSON, filter by today's date
```

Schema after parsing:
```json
{
  "sessions": [{
    "sessionId": "...",
    "createdAt": 1748476800000,
    "conversation": [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."}
    ]
  }]
}
```

### 4. Notion — Meeting Transcripts
**Source:** Notion API via MCP or direct REST

Meetings DB page properties expected:
- `Date` (date property) — filter by today
- `Summary` (rich text) — the transcript summary to inject
- `Title` (title property) — meeting name

```python
# Filter today's meetings
notion.databases.query(
    database_id=config["notion_meetings_db_id"],
    filter={"property": "Date", "date": {"equals": str(date.today())}}
)
```

### 5. Notion — Agent Context Page
**Source:** Notion page (single page, not a DB)

Expected structure (rich text blocks):
```
# Current Focus
[What I'm working on right now — updated manually]

# Active Projects  
[List of projects with brief descriptions]

# This Week's Goals
[Bullet list]

# Background
[Longer context about role, startup stage, etc.]
```

Read via: `notion.pages.retrieve(page_id=config["notion_context_page_id"])`
Then extract all block children as plain text.

---

## Daily Pipeline Logic (`run_daily.py`)

```
run_daily.py is called at 20:00 daily (by cron or OpenClaw)

Step 1 — Collect
  typing_entries  = collect_typing.load_today()          # from daemon JSON
  app_time        = collect_activitywatch.get_today()    # from AW REST API
  cursor_sessions = collect_cursor.get_today()           # from SQLite
  meetings        = collect_notion_meetings.get_today()  # from Notion API
  context         = fetch_context.load()                 # from Notion context page

Step 2 — Pre-process
  typing_by_app   = group_by_app(typing_entries)         # group + dedup
  pie_data        = build_pie_data(app_time)             # top apps by minutes
  cursor_prompts  = extract_user_turns(cursor_sessions)  # user messages only

Step 3 — Summarize
  prompt          = build_prompt(
                      typing_by_app,
                      pie_data,
                      cursor_prompts,
                      meetings,
                      context
                    )
  result          = call_claude(prompt)                  # ~5-8K tokens in, ~800 out
  # result contains: {summary: str, plan: [{id, task, priority}], pie: [...]}

Step 4 — Store
  plan_store.save_plan(result["plan"])                   # ~/.daily-agent/plans/today.json

Step 5 — Deliver
  message = format_telegram_message(result)
  telegram_send.send(message)

Step 6 — Log
  write agent log with token usage, timing, any errors
```

---

## Prompt Engineering (`summarizer.py`)

### System Prompt
```
You are a personal productivity assistant with access to everything the user
actually did today on their computer. Your job is to:
1. Write a concise, semantic daily summary — what was actually accomplished,
   not just what apps were used.
2. Generate a prioritized plan for tomorrow based on today's output,
   unfinished work, and the user's stated goals.

Rules:
- Be direct and specific. Name actual topics, projects, decisions.
- Infer intent from context: "spent 45 min in claude.ai asking about
  architecture" → "Designed system architecture for daily agent project"
- For the plan, output 5-7 concrete tasks, ordered by priority.
- Output strictly valid JSON matching the schema below.
```

### User Prompt Structure (built by `build_prompt()`)
```
TODAY'S DATE: {date}

=== YOUR CONTEXT ===
{context_page_text}

=== TIME BREAKDOWN ===
{pie_data_as_text}
e.g. "Chrome: 3h 20min | Cursor: 2h 10min | Notion: 45min | ..."

=== WHAT YOU TYPED (by app) ===

[claude.ai / ChatGPT / Gemini]
{typing entries for AI tools — your prompts only}

[Cursor IDE]
{cursor user turns from today's sessions}

[Notes / Notion / Word]
{typing entries for writing apps}

[Other apps]
{brief: app name + total typed chars as proxy}

=== MEETINGS TODAY ===
{notion meeting summaries, or "No meetings logged today"}

=== OUTPUT SCHEMA ===
Return ONLY valid JSON:
{
  "summary": "3-5 paragraph narrative of what was accomplished today",
  "highlights": ["key accomplishment 1", "key accomplishment 2", ...],
  "tomorrow_plan": [
    {"id": 1, "task": "...", "priority": "high|medium|low", "context": "why"},
    ...
  ],
  "time_breakdown": [
    {"app": "Chrome", "minutes": 200, "category": "research"},
    ...
  ],
  "blockers": ["anything that seems stuck or unresolved"]
}
```

### Token Budget
- Context page: ~800 tokens
- Time breakdown: ~200 tokens
- Typing entries (filtered): ~1500-2500 tokens
- Cursor sessions (user turns only): ~800 tokens
- Meetings: ~600 tokens
- System + schema: ~500 tokens
- **Total input: ~4500-5500 tokens**
- **Output: ~800-1200 tokens**
- **Daily cost at Claude Sonnet 4: ~$0.015**

---

## Telegram Message Format

```
📊 *Daily Summary — {date}*

{summary paragraph — 3-5 sentences}

✅ *Key Wins*
• {highlight 1}
• {highlight 2}
• {highlight 3}

🕐 *Time Split*
• Chrome / Research: 3h 20m
• Cursor / Code: 2h 10m
• Notion / Writing: 45m

📅 *Tomorrow's Plan*
1. [HIGH] {task} — {context}
2. [HIGH] {task} — {context}
3. [MED] {task} — {context}
4. [MED] {task} — {context}
5. [LOW] {task} — {context}

⚠️ *Watch Out For*
• {blocker 1}

_Reply to edit the plan. Examples:_
_"Move 3 to next week"_
_"Add: review investor deck as priority 1"_
_"Replace 4 with: call with Fernando"_
```

### Plan Edit Parsing
When user replies to the plan message, `telegram_webhook.py` detects edit intent
and calls Claude with a short prompt:

```
Current plan: {json}
User edit request: "{reply_text}"
Return updated plan JSON only. Same schema. No explanation.
```

Saves updated plan back to `plan_store`. Confirms to user: "✓ Plan updated".

---

## OpenClaw Integration (`claw.md`)

The `claw.md` file registers this system as an OpenClaw skill.
It wires the cron trigger, Telegram delivery, and reply handling.
See `claw.md` in root of this repo for the full skill definition.

Key cron entry: `0 20 * * *` (8 PM daily)
Timezone: read from system or `config.yaml`

---

## Configuration (`config.yaml`)

```yaml
# Anthropic
anthropic_api_key: "sk-ant-..."
anthropic_model: "claude-sonnet-4-6"

# Notion
notion_api_key: "secret_..."
notion_meetings_db_id: "..."        # your meetings database ID
notion_context_page_id: "..."       # your "Agent Context" page ID

# Telegram
telegram_bot_token: "..."           # from @BotFather
telegram_chat_id: "..."             # your personal chat ID

# Paths
typing_log_dir: "~/.typing-log"
plans_dir: "~/.daily-agent/plans"
agent_log_dir: "~/daily-agent/logs"

# ActivityWatch
activitywatch_host: "http://localhost:5600"
activitywatch_hostname: ""          # leave empty to auto-detect

# Pipeline
run_hour: 20                        # 8 PM
timezone: "Asia/Jerusalem"          # your timezone

# Filtering — apps to SKIP entirely from typing log
typing_ignore_bundle_ids:
  - "com.apple.keychainaccess"
  - "com.1password.1password"
  - "net.aggimenez.Proxyman"

# Filtering — apps where we want full text (others get char-count only)
typing_deep_apps:
  - bundle_id: "com.google.Chrome"
    domains: ["claude.ai", "chat.openai.com", "gemini.google.com", "aistudio.google.com"]
  - bundle_id: "com.todesktop.230313mzl4w4u92"   # Cursor
    mode: "full"
  - bundle_id: "com.apple.Notes"
    mode: "full"
  - bundle_id: "com.notion.mac"
    mode: "summary"                 # char-count only (content is in Notion already)
```

---

## Implementation Notes & Gotchas

### Typing log deduplication
The daemon may log the same text multiple times if the user edits and re-submits.
`collect_typing.py` must deduplicate by (app, text) within a 5-minute window.
Also filter entries with `len(text) < 10` — likely accidental keystrokes.

### ActivityWatch idle detection
Always intersect window events with the AFK bucket. A user "in Chrome for 3 hours"
may have been idle for 2 of those. Use:
```python
# Only count events where AFK status = "not-afk"
```

### Cursor workspace detection
Multiple workspace folders exist. Filter by `createdAt` timestamp matching today.
Workspaces with no activity today will have old timestamps — skip them.

### Notion API pagination
Meeting DB queries must handle pagination if >100 results (unlikely daily, but safe).

### Claude API error handling
Always catch `anthropic.APIError`. On failure, save raw collected data to
`~/.daily-agent/pending/YYYY-MM-DD.json` so it can be retried manually.

### Telegram message length
Telegram messages are capped at 4096 chars. If summary is longer, split into
two messages: summary first, then plan.

### Security
- `config.yaml` must be `chmod 600`
- Never log API keys or full Notion content to the agent log
- The `typing-ignore-bundle_ids` list must include password managers

---

## What Is Already Built

| Component | Status |
|---|---|
| Typing daemon | ✅ DONE — do not modify |
| `~/.typing-log/YYYY-MM-DD.json` schema | ✅ DONE |
| `config.yaml` template | ✅ in this repo |
| Everything else | 🔧 TO BUILD |

## Build Order (follow this sequence)

1. `config.yaml` — fill in all keys before anything else
2. `collectors/collect_typing.py` — verify you can read + filter today's log
3. `collectors/collect_activitywatch.py` — verify AW is running, check bucket names
4. `collectors/collect_cursor.py` — verify SQLite paths on your machine
5. `collectors/collect_notion_meetings.py` — verify Notion DB IDs
6. `context/fetch_context.py` — verify context page reads correctly
7. `pipeline/summarizer.py` — test with dummy data first, check token counts
8. `pipeline/run_daily.py` — wire all collectors together, test end-to-end
9. `delivery/telegram_send.py` — test message formatting
10. `delivery/telegram_webhook.py` — test plan edit flow
11. `claw.md` — wire OpenClaw cron + Telegram channel
12. End-to-end test, then enable cron

## Testing

```bash
# Test a single collector
python collectors/collect_typing.py --date 2026-05-29 --dry-run

# Test full pipeline without sending Telegram
python pipeline/run_daily.py --date 2026-05-29 --dry-run

# Test with a specific date's data
python pipeline/run_daily.py --date 2026-05-28 --send

# Test plan edit parsing
python delivery/telegram_webhook.py --test "move item 2 to next week"
```
