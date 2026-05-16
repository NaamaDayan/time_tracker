# Time & Habit Tracker — Cursor Development Guide

This file is the source of truth for how to build this project. Read `app_description.md` for product goals; follow this file for architecture, conventions, and implementation order.

---

## Product goals (summary)

1. **Time truth**: For any configurable window (day / week / month), show what actually happened in each time slot (sleep, walk, read, work, etc.).
2. **Habits & goals**: Track completion % automatically from integrated data — no manual “did I do it?” logging.

**Constraints that shape the design**

- Activities can **overlap** (e.g. bus + reading). The data model must support multiple labels on the same interval, not force a single winner.
- Sources are **heterogeneous** (Clockify, phone usage, watch, Hevy, Lithium, Spotify, YouTube, Google Calendar; location later).
- MVP uses **real integrations** listed in `app_description.md`; infer rules can be crude (e.g. laptop on → Work) and refined later.

---

## Principles (read before every change)


| Principle                      | What it means in practice                                                                                                                   |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Local first**                | Run API, worker, DB, and UI on the machine via Docker Compose. No AWS dependency until core flows work.                                     |
| **AWS-shaped, not AWS-locked** | Use Postgres, env-based config, stateless API, object storage for exports — maps cleanly to RDS, ECS/Lambda, S3 later.                      |
| **Affordable**                 | Prefer boring OSS, one small Postgres instance, batch sync jobs over always-on pollers, and managed services only when they save real time. |
| **Raw → normalized → windows**   | Never lose vendor payloads. `RawEvent` → classify to `ActivitySegment` → gap-merge to `ActivityWindow`. Raw is never modified by aggregation. |
| **Idempotent ingestion**       | Every connector sync must be safe to re-run (upsert on stable external IDs).                                                                |
| **Explicit time zones**        | Store UTC in DB; convert at API/UI using user timezone (default from env).                                                                  |
| **Small MVP slices**           | One connector end-to-end (fetch → store → classify → week view) before adding the next.                                                     |


---

## Recommended stack (MVP → production)

Adjust only with a good reason documented in the PR/commit message.


| Layer                | Choice                                                                                                             | Why                                                                        |
| -------------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| **API**              | Python 3.12 + **FastAPI**                                                                                          | Strong fit for ETL, date/time, and future ML/rules; simple OpenAPI for UI. |
| **Jobs**             | Same repo: **APScheduler** or Celery later; MVP can use FastAPI background tasks + CLI `sync` commands             | Avoid Celery/Redis until you need it.                                      |
| **DB**               | **PostgreSQL 16** (Docker locally)                                                                                 | Same engine as RDS; JSONB for raw payloads.                                |
| **ORM / migrations** | **SQLAlchemy 2** + **Alembic**                                                                                     |                                                                            |
| **Frontend**         | **Next.js** (App Router) + TypeScript                                                                              | Week/day timeline UI; API client from OpenAPI if desired.                  |
| **Auth (later)**     | Session or JWT behind reverse proxy; MVP can be single-user with API key in `.env`                                 |                                                                            |
| **AWS (later)**      | RDS Postgres, S3 (raw exports/backups), ECS Fargate or App Runner for API, EventBridge + Lambda for scheduled sync | Start with one environment; no multi-region.                               |


**Do not use** a heavy framework or microservices split until a monolith + Postgres is clearly insufficient.

---

## Repository layout (create as you build)

```
time_tracker_cursor/
├── CURSOR.md
├── app_description.md
├── docker-compose.yml          # postgres (+ optional api/ui)
├── .env.example
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── models/             # SQLAlchemy
│   │   ├── schemas/            # Pydantic
│   │   ├── connectors/         # one module per source
│   │   ├── pipeline/           # classify, normalize, windows (gap-merge), aggregate (overlap totals)
│   │   └── api/                # routes
│   ├── alembic/
│   └── tests/
├── frontend/
│   └── ...
└── scripts/
    └── sync_all.sh             # local cron-friendly entrypoint
```

---

## Core data model

Implement these concepts early; most features hang off them.

### 1. `SourceAccount`

Links a user to an integration (`clockify`, `google_calendar`, `spotify`, `hevy`, `samsung_health`, etc.) with encrypted tokens in DB or references to env secrets for MVP.

### 2. `RawEvent`

- `source`, `external_id` (unique per source), `occurred_at` / `ended_at`, `payload` (JSONB), `ingested_at`
- Immutable after insert except dedupe fixes

### 3. `ActivitySegment` (Layer 2 — classification)

- One row per raw event (or manual entry): `started_at`, `ended_at`, `activity_type_slug`, `confidence`, `source`, `metadata`, optional `raw_event_id`
- Multiple segments **may overlap** the same clock time (different activity types)
- Rebuilt when raw events sync; manual segments via `POST/PATCH/DELETE /segments`

### 4. `ActivityWindow` (Layer 3 — presentation)

- Gap-merged intervals for UI: `activity_windows` + `activity_window_segments` (provenance junction)
- **Merge key**: `activity_type_slug` only — cross-source (Clockify + Calendar + manual with same type merge together)
- **Merge rule**: consecutive segments merge if `gap = next.start - current.end <= ACTIVITY_MERGE_GAP_MINUTES` (inclusive), or if intervals overlap (union)
- Raw segments are never modified; windows are **recomputed** incrementally when segments change
- Config: `ACTIVITY_MERGE_GAP_MINUTES` (default 5); snapshot stored in window `metadata.merge_gap_minutes`
- Code: `backend/app/pipeline/windows/` (`merge.py` pure, `recompute.py` + `service.py` DB)
- Backfill: `python -m app.pipeline.windows.cli backfill [--from ISO] [--to ISO]`

### 5. `ActivityType` (configurable)

Seed from spec: `sleep`, `sport`, `read`, `work`, `fun`, `consuming`, `transport`, `communication`, `eat`, `screen_time` (phone/laptop aggregate). Allow user-defined types later via DB seed + admin UI.

### 6. `HabitGoal`

- Rule definition (e.g. “≥ 7h sleep”, “≥ 8k steps”, “≥ 30 min read/day”, “work apps < 4h on weekends”)
- Computed `daily_score` / `weekly_score` from segments today (windows later) — not manual check-ins

### Classification

- **Rules engine (MVP)**: declarative mapping (source + app name + calendar title → activity type)
- Keep rules in DB or versioned YAML under `backend/app/rules/`; unit-test each rule

### Pipeline flow (three layers)

```
Connectors → raw_events (immutable)
              ↓ classify (rules YAML)
         activity_segments (fragmented; may overlap across types)
              ↓ gap-merge per activity_type_slug
         activity_windows ← activity_window_segments (provenance)
```

| Layer | Table | API |
|-------|--------|-----|
| 1 Raw | `raw_events` | — |
| 2 Segments | `activity_segments` | `GET /timeline` |
| 3 Windows | `activity_windows` | `GET /windows` |

---

## MVP integrations (priority order)

Build in this order unless blocked by API access:


| Priority | Source                | MVP behavior                                                                                 | Notes                                                 |
| -------- | --------------------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| P0       | **Clockify**          | Laptop active time → `work` (whole interval)                                                 | Official API; API key in `.env`                       |
| P0       | **Google Calendar**   | Events → `communication` (if at least 1 more attendees in meeting). else - currently ignore. | OAuth; assume scheduled duration is actual (per spec) |
| P1       | **Spotify**           | Listening sessions → `consuming`; tag podcast vs music in metadata                           | Web API OAuth                                         |
| P1       | **YouTube**           | Watch history count / sessions → `consuming`                                                 | Google OAuth (YouTube Data API)                       |
| P1       | **Hevy**              | Workouts → `sport` with duration. not in mvp.                                                | Check for official/unofficial API; store raw JSON     |
| P2       | **Lithium** (reading) | Pages / book per day → `read` not in mvp.                                                    | Confirm export/API; if none, CSV import connector     |
| P2       | **Samsung phone**     | Per-app foreground timestamps → `screen_time` + app-based rules. can use ActivityWatch app.  | use activityWatch app. check for official free api.   |
| P2       | **Samsung Watch**     | Sleep + steps/workouts via **Samsung Health**                                                | Samsung Health SDK / export; document consent scopes  |
| P3       | **Location**          | Home / office / restaurant / beach / transit inference - currently not in mvp.               | See location section below                            |


**Suggested extra connectors** (easy wins): **Strava** (sport), **Goodreads** (read), **RescueTime** (app time on desktop — overlaps Clockify).

---

## Location (post-MVP but design for it)

Google Timeline has **no supported read API** for personal use. Do not block MVP on it.

**Affordable options (pick one path in a later phase)**

1. **OwnTracks** (MQTT) or **Home Assistant** — self-hosted, privacy-friendly, good for home/office geofences.
2. **Custom Android foreground service** — periodic fused location (e.g. 15–30 min or geofence triggers); upload to your API over HTTPS; battery: use `WorkManager` + significant motion/geofence, not continuous GPS.
3. **Google Takeout** batch import — not “last day” realtime; OK for backfill only.

Store location as `RawEvent` + derived `place_label` segments; never commit API keys or location blobs to git.

---

## Parallel activities & presentation

- **Storage**: overlapping `ActivitySegment` rows are allowed across **different** activity types (e.g. transport + read at once).
- **Windows**: gap-merge runs **per activity type**; different types keep separate overlapping windows.
- **API reads**:
  - `GET /timeline` — raw classified segments (debug, manual CRUD, provenance)
  - `GET /windows` — gap-merged `ActivityWindow` list with `segment_ids` provenance
  - `GET /aggregate` — pie-chart totals; overlap **priority** via `overlap.yaml` (read-time only, not windows)
- **UI (target)**: calendar uses `/windows` for clean blocks; `/timeline` for drill-down. Merged-window edit deferred when a window spans multiple manual segments.
- **Incremental recompute**: after sync (`rebuild_segments_for_raw_events`) or manual segment CRUD — invalidate padded range `[min(start)-gap, max(end)+gap]` per touched type, delete overlapping windows, re-merge segments in range.
- **Do not confuse**: `pipeline/aggregate.py` (overlap winner for habit %) ≠ `pipeline/windows/` (gap merge for timeline).

---

## Local development

### Requirements

- Docker & Docker Compose
- Python 3.12+, Node 20+ (when frontend exists)
- `direnv` or manual `.env` copy from `.env.example`

### Docker Compose (minimum)

- Service `db`: Postgres 16, volume `pgdata`, port `5432`
- Optional: `api` and `web` services once Dockerfiles exist

### Environment variables (`.env.example` — never commit real secrets)

```
DATABASE_URL=postgresql://tracker:tracker@localhost:5432/time_tracker
USER_TIMEZONE=Asia/Jerusalem
CLOCKIFY_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
# Single-user MVP
API_KEY=dev-only-change-me

# Gap-merge threshold for activity windows (same activity type, cross-source)
ACTIVITY_MERGE_GAP_MINUTES=5
```

### Commands (target conventions)

```bash
docker compose up -d db
cd backend && alembic upgrade head
uvicorn app.main:app --reload
# Per connector
python -m app.connectors.clockify sync --since 7d
# Rebuild activity windows from all segments (after migration or config change)
python -m app.pipeline.windows.cli backfill
```

### Testing

- **pytest** for connectors (fixtures = recorded JSON payloads), pipeline, and habit scoring
- No live API calls in CI; use VCR/fixtures

---

## AWS deployment (later — do not implement until local MVP works)

Target **low cost ~$30–80/mo** for single-user:


| Component | Service                                                      |
| --------- | ------------------------------------------------------------ |
| DB        | RDS Postgres `db.t4g.micro` or small `db.t4g.small`          |
| API       | ECS Fargate (0.25 vCPU) **or** App Runner                    |
| Sync cron | EventBridge → Lambda invoking sync **or** ECS scheduled task |
| Secrets   | AWS Secrets Manager (OAuth refresh tokens)                   |
| Static UI | S3 + CloudFront **or** Vercel (cheaper for frontend only)    |
| Backups   | RDS snapshots + optional S3 export of `RawEvent`             |


**Migration path**: same Postgres schema; `DATABASE_URL` from Secrets Manager; run Alembic on deploy.

---

## Security & privacy

- This app handles **sensitive life data**. Treat all timelines, health, and location as confidential.
- Encrypt tokens at rest; use HTTPS only in production.
- Minimal scopes per OAuth provider; document what each connector reads.
- Provide a **delete all data for source X** path early.
- Do not log full `RawEvent` payloads in production logs.

---

## API & frontend conventions

- REST JSON under `/api/v1/`
- Key endpoints: `GET /timeline?from=&to=` (segments), `GET /windows?from=&to=` (merged), `GET /aggregate?from=&to=`, `POST /sync`, `POST/PATCH/DELETE /segments` (manual)
- OpenAPI at `/docs` in dev only (or behind auth in prod)
- Frontend: week view first, then day drill-down; use user timezone for bucketing

---

## Using Cursor effectively on this project

### What to put in prompts

- Reference `**app_description.md`** for *what* and `**CURSOR.md*`* for *how*.
- One task per session when possible: e.g. “Clockify connector + RawEvent + tests” not “build entire app”.
- Include: date range, timezone, sample API response or fixture file, and acceptance criteria.

### MCP / connectors

- Use MCP for **docs and API exploration** (OAuth steps, field lists), not as the runtime ingestion path unless it’s a maintained official integration.
- Runtime ingestion = code in `backend/app/connectors/`.

### Phased build order (for agents and humans)

1. Docker Postgres + Alembic + `RawEvent` / `ActivitySegment` / `ActivityWindow` models
2. Clockify sync → normalize → windows recompute → `GET /timeline` + `GET /windows`
3. Google Calendar sync + naive classification
4. Minimal Next.js week grid (wire calendar to `/windows` when ready)
5. Spotify + YouTube + Hevy
6. Habit rules + weekly % API
7. Samsung / location (hardest — spike before committing)

---

## Code style

- **Python**: type hints, ruff, black; async only where it helps (HTTP clients)
- **TypeScript**: strict mode, ESLint + Prettier
- **SQL**: migrations only via Alembic; no hand-editing prod DB
- **Commits**: small, focused; message explains *why*
- **No drive-by refactors**; match existing patterns in the repo

---

## Definition of done (MVP)

- Local Postgres + migrations run cleanly on a fresh clone  
- At least **Clockify + Google Calendar** sync into `RawEvent` and appear on a **week timeline**  
- Overlapping segments visible or documented as limitation with clear UI copy  
- At least **3 habit goals** computed automatically from data  
- `.env.example` documents all required keys; no secrets in git  
- README with local setup (separate from this file) when scaffold exists

---

## Out of scope for MVP (do not build yet)

- Google Timeline realtime sync  
- Perfect calendar duration (Meet/GPS cross-check)  
- Multi-user accounts / billing  
- Mobile app (unless needed as a thin location uploader)  
- Claude Cowork / multi-agent orchestration — standard Cursor + this repo is enough

---

## When unsure

1. Prefer storing **raw** data and iterating **rules** over re-fetching.
2. Prefer **Postgres + batch sync** over realtime streams.
3. Ask in the PR/issue which `ActivityType` should win when rules conflict; encode in tests.
4. If a vendor has no API (Samsung app usage), propose **export file import** or a **small companion app** before scraping.

