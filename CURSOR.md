# Time & Habit Tracker — Cursor Development Guide

This file is the source of truth for how to build this project. Read `app_description.md` for product goals; follow this file for architecture, conventions, and implementation order.

---

## Product goals (summary)

1. **Time truth**: For any configurable window (day / week / month), show what actually happened in each time slot (sleep, walk, read, work, etc.).
2. **Habits & goals**: Track completion % automatically from integrated data — no manual “did I do it?” logging.

**Constraints that shape the design**

- Activities can **overlap** (e.g. bus + reading). The data model must support multiple labels on the same interval, not force a single winner.
- Sources are **heterogeneous** (ActivityWatch Desktop, phone usage, watch, Hevy, Lithium, Spotify, YouTube, Google Calendar, **location** via geofence + Dawarich).
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
| **Jobs**             | **APScheduler** in-process (Dawarich daily pull); CLI `sync` commands; `scripts/sync_all.sh` for cron              | Celery/Redis only if you outgrow this.                                     |
| **Location store**   | **[Dawarich](https://dawarich.app/)** (Docker, self-hosted) for raw GPS + visit detection                         | Backend pulls visits; phone POSTs points directly to Dawarich.             |
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
├── docker-compose.yml          # time_tracker db + Dawarich stack (app/db/redis/sidekiq)
├── docker/dawarich.env.example
├── .env.example
├── backend/
│   ├── app/
│   │   ├── main.py             # lifespan starts APScheduler
│   │   ├── scheduler.py        # Dawarich daily sync
│   │   ├── models/             # SQLAlchemy
│   │   ├── schemas/            # Pydantic
│   │   ├── connectors/         # activitywatch, google_calendar, dawarich, geofence, …
│   │   ├── pipeline/           # classify, normalize, rule_config, windows, aggregate, net
│   │   ├── rules/              # *.yaml per source (incl. location_zones, dawarich)
│   │   ├── seed_rule_configs.py
│   │   └── api/                # routes, settings/ (zones, rule-configs), integrations
│   ├── alembic/
│   └── tests/
├── companion-android/          # Samsung Health, Activity Watch, location (GPS/geofence)
│   └── app/src/main/assets/geofence_zones.json
├── frontend/
│   ├── app/settings/           # layout + sidebar; rules, zones
│   ├── lib/activityRegistry.ts # emoji/recipes; labels from API activity-types
│   └── lib/settingsNav.ts      # sidebar section list
└── scripts/
    └── sync_all.sh             # local cron-friendly entrypoint
```

---

## Core data model

Implement these concepts early; most features hang off them.

### 1. `SourceAccount`

Links a user to an integration (`activitywatch_desktop`, `google_calendar`, `activitywatch`, `samsung_health`, `geofence`, `dawarich`, etc.) with encrypted tokens in DB or references to env secrets for MVP.

### 2. `RawEvent`

- `source`, `external_id` (unique per source), `occurred_at` / `ended_at`, `payload` (JSONB), `ingested_at`
- Immutable after insert except dedupe fixes

### 3. `ActivitySegment` (Layer 2 — classification)

- One row per raw event (or manual entry): `started_at`, `ended_at` (nullable for **open** geofence visits), `activity_type_slug`, `confidence`, `source`, `metadata`, optional `raw_event_id`
- Multiple segments **may overlap** the same clock time (different activity types)
- Rebuilt when raw events sync (`rebuild_segments_for_raw_events`); **geofence** uses custom open/close on ENTER/EXIT; manual segments via `POST/PATCH/DELETE /segments`
- Open segments (`ended_at IS NULL`) appear on `GET /timeline` (clipped to query `to`); excluded from window gap-merge until closed

### 4. `ActivityWindow` (Layer 3 — presentation)

- Gap-merged intervals for UI: `activity_windows` + `activity_window_segments` (provenance junction)
- **Merge key**: `activity_type_slug` only — cross-source (ActivityWatch Desktop + Calendar + manual with same type merge together)
- **Merge rule**: consecutive segments merge if `gap = next.start - current.end <= merge_gap_minutes` (inclusive), or if intervals overlap (union)
- Raw segments are never modified; windows are **recomputed** incrementally when segments change
- **Gap source**: per-type `activity_rule_configs.merge_gap_minutes` when set; else env `ACTIVITY_MERGE_GAP_MINUTES` (default 5). Snapshot stored in window `metadata.merge_gap_minutes`
- Code: `backend/app/pipeline/windows/` (`merge.py` pure, `recompute.py` + `service.py` DB)
- Backfill: `python -m app.pipeline.windows.cli backfill [--from ISO] [--to ISO]`

### 5. `ActivityType` (configurable)

Seed from spec: `sleep`, `sport`, `read`, `work`, `fun`, `consuming`, `transport`, `communication`, `eat`, `screen_time`, `phone_usage`, `music_podcast`. Allow user-defined types later via DB seed + admin UI.

### 6. `HabitGoal`

- Rule definition (e.g. “≥ 7h sleep”, “≥ 8k steps”, “≥ 30 min read/day”, “work apps < 4h on weekends”)
- Computed `daily_score` / `weekly_score` from segments today (windows later) — not manual check-ins

### Classification

- **Rules engine (MVP)**: declarative mapping per `source` in YAML under `backend/app/rules/` — logic is fixed; tunable thresholds live in DB (see below)
- Sources with rules today: `activitywatch_desktop` (`activitywatch_desktop.yaml`), `google_calendar`, `samsung_health`, `activitywatch`, `geofence` (`location_zones.yaml`), `dawarich` (`dawarich.yaml`)
- `classify_raw_event_safe(source, payload, db=…, started_at=…, ended_at=…)` returns `None` when activity is null (e.g. `home`), type is **disabled**, below **min_duration**, or outside **work** schedule (desktop work only)
- After classify, `apply_rule_config_filters` reads `activity_rule_configs` via cached `get_rule_config(slug, db)` (`pipeline/rule_config.py`, 60s TTL; invalidate on PATCH)
- Unit-test each rule file; fixtures under `backend/tests/fixtures/`

### 7. `ActivityRuleConfig` (per-type parameters — implemented)

One row per activity type (14 seeded types). Users tune via **Settings → Activity rules**; YAML rules are not edited in UI.

| Column | Purpose |
|--------|---------|
| `activity_type_slug` | FK → `activity_types`, unique |
| `enabled` | `false` → classifier skips this type |
| `min_duration_minutes` | Drop segments shorter than this (when `ended_at` known) |
| `merge_gap_minutes` | Overrides global gap for window merge for this type |
| `boost_signals` | JSONB toggles (e.g. `watch_active`, `hevy_open` for sport) |
| `custom_params` | JSONB (e.g. `work_days`, `work_hours_start/end`, `max_duration_minutes` for bathroom) |

- **Model:** `backend/app/models/activity_rule_config.py`
- **Seed:** migration `010_add_activity_rule_configs` + `seed_rule_configs(db)` on API startup if table empty (`backend/app/seed_rule_configs.py`)
- **API:** `GET/PATCH /api/v1/settings/rule-configs/`, `GET …/{slug}/preview?from=&to=` (dry-run segment stats, default last 7 days; no window recompute)
- **Tests:** `backend/tests/test_rule_configs.py`

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
| P0       | **ActivityWatch Desktop** | Laptop active time → `work` (app/window rules)                                           | Local REST API at `localhost:5600`; polls `aw-watcher-window` + `aw-watcher-afk` |
| P0       | **Google Calendar**   | Events → `communication` (if at least 1 more attendees in meeting). else - currently ignore. | OAuth; assume scheduled duration is actual (per spec) |
| P1       | **Spotify**           | Listening sessions → `consuming`; tag podcast vs music in metadata                           | Web API OAuth                                         |
| P1       | **YouTube**           | Watch history count / sessions → `consuming`                                                 | Google OAuth (YouTube Data API)                       |
| P1       | **Hevy**              | Workouts → `sport` with duration. not in mvp.                                                | Check for official/unofficial API; store raw JSON     |
| P2       | **Lithium** (reading) | Pages / book per day → `read` not in mvp.                                                    | Confirm export/API; if none, CSV import connector     |
| P2       | **Samsung phone**     | Per-app usage via **Activity Watch** → companion ingest → app rules (`communication`, `consuming`, `read`, `transport`, `music_podcast`, `phone_usage`). | `POST /integrations/activitywatch/ingest`; rules in `activitywatch.yaml`. |
| P2       | **Samsung Watch**     | Sleep + steps/workouts via **Samsung Health**                                                | Samsung Health SDK / export; document consent scopes  |
| P2       | **Location (geofence)** | Named zones (home, office, gym, …) → place visits via hardware geofences + instant backend ingest | `POST /integrations/location/geofence`; rules `location_zones.yaml`; companion `geofence_zones.json` |
| P2       | **Location (Dawarich)** | GPS points → Dawarich; daily visit pull → segments for inferred places (restaurant, transit, …) | `connectors/dawarich/`; rules `dawarich.yaml`; APScheduler @ `DAWARICH_SYNC_HOUR` |


**Suggested extra connectors** (easy wins): **Strava** (sport), **Goodreads** (read), **RescueTime** (app time on desktop — overlaps ActivityWatch Desktop).

---

## Location (implemented)

Google Timeline has **no supported read API** for personal use. This project uses **Dawarich + the existing Android companion** instead.

### Architecture

```
companion-android
  ActivityRecognition → STILL: geofences only | MOVING: fused GPS every 5 min
  GeofencingClient    → ENTER/EXIT → POST backend …/location/geofence (immediate)
  DawarichClient      → batched points → POST Dawarich …/owntracks/points (Wi‑Fi / 15 min)

Dawarich (Docker)     → raw points, visit detection (Sidekiq), reverse geocode

backend
  geofence ingest     → RawEvent source=geofence → open/close ActivitySegment
  DawarichConnector   → GET /api/v1/visits daily → RawEvent source=dawarich → classify → segments
```

**Battery model:** GPS only while Activity Recognition reports movement; hardware geofences always on. Target ~2–3%/day on Samsung.

### Data paths

| Layer | `source` | How it arrives | Classification |
|-------|----------|----------------|----------------|
| Geofence event | `geofence` | Phone → `POST /api/v1/integrations/location/geofence` | `location_zones.yaml` (zone name → activity; `home` → no segment) |
| Dawarich visit | `dawarich` | Backend pull `GET {DAWARICH_BASE_URL}/api/v1/visits` | `dawarich.yaml` (OSM tags / place name → activity) |

**Dedup:** If a Dawarich visit overlaps a geofence segment ≥70% (same place name), **geofence wins** — Dawarich raw is stored but segment is skipped (`_deduped_by_geofence` in payload).

### Key files

- Rules: `backend/app/rules/location_zones.yaml`, `backend/app/rules/dawarich.yaml`, `backend/app/rules/zone_category_defaults.py`
- Backend: `backend/app/connectors/geofence/`, `backend/app/connectors/dawarich/`, `backend/app/api/location.py`, `backend/app/api/settings/zones.py`, `backend/app/api/settings/rule_configs.py`, `backend/app/pipeline/geo.py`, `backend/app/scheduler.py`
- Model: `backend/app/models/gps_zone.py`
- Frontend: `frontend/app/settings/zones/`, `frontend/components/zones/`
- Android zones: `companion-android/app/src/main/assets/geofence_zones.json` (edit lat/lon/radius; rebuild APK)
- Migrations: `007_location_open_segments`, `009_add_gps_zones`, `010_add_activity_rule_configs`

### Env vars

`DAWARICH_BASE_URL`, `DAWARICH_API_KEY`, `DAWARICH_SYNC_ENABLED`, `DAWARICH_SYNC_HOUR`, `LOCATION_GEOFENCE_ENABLED` — see `.env.example`. **First login:** with `RAILS_ENV=production` (our compose default), create an admin via `docker exec -it dawarich_app bin/rails console` → `User.create!(email:, password:, password_confirmation:, admin: true)` — see root `README.md`. API key from Dawarich UI (Settings → API key). Phone uses **two keys**: Dawarich key for points, `API_KEY` for geofence ingest.

### APIs (location)

- `POST /api/v1/integrations/location/geofence` — `{ zone_name, transition, lat, lon, timestamp }`
- `GET /api/v1/integrations/location/status`
- `POST /api/v1/sync/dawarich` — manual visit pull
- `DELETE /api/v1/sources/{source}/data` — purge `geofence` or `dawarich` (privacy)

Place visits surface on **`GET /timeline`** and **`GET /windows`** like other activity types (`sport`, `eat`, `transport`, `work`, `fun`).

### GPS Zones (implemented)

Named places configured via the **Settings → GPS Zones** UI (`/settings/zones`). Zones are stored in the `gps_zones` table (UUID PK) and drive geofence classification at runtime.

**Model:** `backend/app/models/gps_zone.py` — `name` (unique), `category` (home/work/gym/family/social/transit/other), `activity_type_slug` (FK → activity_types, auto-filled from category defaults), `lat`, `lon`, `radius_meters`, `enabled`.

**Category → activity defaults:** `backend/app/rules/zone_category_defaults.py` (work→work, gym→sport, family→fun, social→fun, transit→transport, home/other→null).

**APIs:** `GET/POST /api/v1/settings/zones/`, `PATCH/DELETE /api/v1/settings/zones/{id}`. Also `POST /api/v1/activity-types` to create new types from the UI.

**Classifier integration:** `classify_geofence_event(payload, db=session)` looks up zones by name (or by lat/lon via Haversine) in DB first, falls back to `location_zones.yaml`.

**Geo helper:** `backend/app/pipeline/geo.py` — `haversine_meters(lat1, lon1, lat2, lon2)`, `get_zone_for_point(lat, lon, db)` (nearest enabled zone within radius).

**Frontend:** Leaflet map at `/settings/zones` (see **Settings UI** below). Migration: `009_add_gps_zones` (seeds initial zones from `geofence_zones.json`).

**Not implemented yet:** habit rules on visit count (e.g. ≥3 gym/week), live map in Time Tracker UI, multi-user location.

### Settings UI (implemented)

Gear icon → `/settings`. **Left sidebar** for sections (scales to more config pages); main panel is page content.

| Route | Purpose |
|-------|---------|
| `/settings` | Overview cards |
| `/settings/rules` | Per-type sliders/toggles; auto-save (800ms debounce); preview last 7 days |
| `/settings/zones` | GPS zone map + address search (search overlays map only, not sidebar) |

- **Nav registry:** `frontend/lib/settingsNav.ts` — add new sidebar entries here
- **Activity display names:** labels/colors from `GET /activity-types`; emoji + recipe copy from `frontend/lib/activityRegistry.ts` (`resolveActivityDisplay`)
- **Rules UI:** `frontend/components/rules/ActivityRuleCard.tsx`, `WorkHoursRange.tsx` (single dual-handle work-hours slider; start before end enforced)
- **Not implemented yet:** bulk reset to defaults, import/export rule configs, per-zone rule overrides, conflict detection between types

---

## Parallel activities & presentation

- **Storage**: overlapping `ActivitySegment` rows are allowed across **different** activity types (e.g. transport + read at once).
- **Windows**: gap-merge runs **per activity type**; different types keep separate overlapping windows.
- **API reads**:
  - `GET /timeline` — raw classified segments (debug, manual CRUD, provenance)
  - `GET /windows` — **bruto** gap-merged `ActivityWindow` list with `segment_ids` provenance
  - `GET /aggregate` — **pie chart** overlap totals via `overlap.yaml` (read-time only, not windows)
  - `GET /net` — **neto** additive totals per activity type (overlaps double-count)
- **UI views** (must match API semantics):
  - **Calendar view (bruto)** → `GET /windows`. Same-type segments merge when gap ≤ per-type `merge_gap_minutes` (or global `ACTIVITY_MERGE_GAP_MINUTES`). Short windows hidden on read per global gap. Overlapping types may appear as parallel blocks.
  - **Pie chart view** → `GET /aggregate`. Each instant has one winner (`overlap.yaml`). Slices + unattributed must sum to **100% of 24h × calendar days** in range (user timezone); unattributed fills idle time.
  - **Net view (neto)** → `GET /net`. Sum clipped segment durations per type; overlaps add up (can exceed 24h/day). Grouped by activity type only.
- **Incremental recompute**: after sync (`rebuild_segments_for_raw_events`) or manual segment CRUD — invalidate padded range `[min(start)-gap, max(end)+gap]` per touched type, delete overlapping windows, re-merge segments in range.
- **Do not confuse**: `pipeline/aggregate.py` (overlap winner, 24h budget) ≠ `pipeline/net.py` (additive) ≠ `pipeline/windows/` (gap merge for calendar).

---

## Local development

### Requirements

- Docker & Docker Compose
- Python 3.12+, Node 20+ (when frontend exists)
- `direnv` or manual `.env` copy from `.env.example`

### Docker Compose

- **`db`**: Postgres 16 for Time Tracker (`time_tracker`), port `5432`
- **`dawarich_*`**: `dawarich_app` (port `3000`), `dawarich_db` (PostGIS), `dawarich_redis`, `dawarich_sidekiq`
- **Apple Silicon:** `dawarich_db` defaults to `imresamu/postgis:17-3.5-alpine` (see `docker-compose.yml`)
- API and frontend run on the host (not in compose for MVP)

### Environment variables (`.env.example` — never commit real secrets)

```
DATABASE_URL=postgresql+psycopg://tracker:tracker@localhost:5432/time_tracker
USER_TIMEZONE=Asia/Jerusalem
API_KEY=dev-only-change-me
ACTIVITYWATCH_BASE_URL=http://127.0.0.1:5600
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
ACTIVITY_MERGE_GAP_MINUTES=5

# Location
FRONTEND_URL=http://localhost:3001
DAWARICH_BASE_URL=http://localhost:3000
DAWARICH_API_KEY=
DAWARICH_SYNC_ENABLED=true
DAWARICH_SYNC_HOUR=2
LOCATION_GEOFENCE_ENABLED=true
```

Full list: `.env.example`. Setup steps: root `README.md` (Dawarich + companion-android).

### Commands (target conventions)

```bash
docker compose up -d db
docker compose up -d dawarich_db dawarich_redis dawarich_app dawarich_sidekiq   # optional: location
cd backend && alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Per connector
python -m app.connectors.activitywatch sync --since 7d
python -m app.connectors.dawarich.cli sync --since 2d
./scripts/sync_all.sh 7d    # includes Dawarich when DAWARICH_API_KEY is set
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
- Provide a **delete all data for source X** path early (`DELETE /api/v1/sources/{source}/data` for `geofence`, `dawarich`, etc.).
- Do not log full `RawEvent` payloads in production logs.

---

## API & frontend conventions

- REST JSON under `/api/v1/`
- Key endpoints: `GET /timeline`, `GET /windows`, `GET /aggregate`, `GET /net`, `POST /sync`, `POST /sync/dawarich`, `POST/PATCH/DELETE /segments`
- Settings: `GET/PATCH /api/v1/settings/rule-configs/`, `GET …/{slug}/preview`; `GET/POST/PATCH/DELETE /api/v1/settings/zones/`
- Integrations (push, `X-API-Key`): `POST /integrations/samsung/ingest`, `POST /integrations/activitywatch/ingest`, `POST /integrations/location/geofence`
- OpenAPI at `/docs` in dev only (or behind auth in prod)
- Frontend: week view first, then day drill-down; use user timezone for bucketing

---

## Using Cursor effectively on this project

### What to put in prompts

- Reference `**app_description.md`** for *what* and `**CURSOR.md*`* for *how*.
- One task per session when possible: e.g. “ActivityWatch connector + RawEvent + tests” not “build entire app”.
- Include: date range, timezone, sample API response or fixture file, and acceptance criteria.

### MCP / connectors

- Use MCP for **docs and API exploration** (OAuth steps, field lists), not as the runtime ingestion path unless it’s a maintained official integration.
- Runtime ingestion = code in `backend/app/connectors/`.

### Phased build order (for agents and humans)

1. Docker Postgres + Alembic + `RawEvent` / `ActivitySegment` / `ActivityWindow` models — **done**
2. ActivityWatch Desktop sync → windows → `GET /timeline` + `GET /windows` — **done**
3. Google Calendar sync + classification — **done**
4. Samsung Health + Activity Watch (companion push ingest) — **done**
5. **Location**: Dawarich Docker + geofence ingest + DawarichConnector + companion GPS — **done**; habit visit-count rules — later
6. **GPS Zones config**: DB-backed zones, CRUD API, Leaflet settings UI, Haversine classifier — **done**
7. **Activity rule configs**: DB params, classifier/window integration, rules settings UI + sidebar — **done**
8. Minimal Next.js week grid (calendar / pie / net) — **partial**
9. Habit rules + weekly % API — **done** (ActivityWatch-based goals)
10. Spotify + YouTube + Hevy — not started

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
- At least **ActivityWatch Desktop + Google Calendar** sync into `RawEvent` and appear on a **week timeline**  
- Overlapping segments visible or documented as limitation with clear UI copy  
- At least **3 habit goals** computed automatically from data  
- `.env.example` documents all required keys; no secrets in git  
- README with local setup (separate from this file) when scaffold exists

---

## Out of scope for MVP (do not build yet)

- Google Timeline realtime sync  
- Perfect calendar duration (Meet/GPS cross-check)  
- Multi-user accounts / billing  
- Real-time location WebSocket / live map in Time Tracker UI  
- Habit goals from geofence visit counts (e.g. gym 3×/week) — data exists, rules not wired  
- Claude Cowork / multi-agent orchestration — standard Cursor + this repo is enough

---

## When unsure

1. Prefer storing **raw** data and iterating **rules** over re-fetching.
2. Prefer **Postgres + batch sync** over realtime streams.
3. Ask in the PR/issue which `ActivityType` should win when rules conflict; encode in tests.
4. If a vendor has no API (Samsung app usage), propose **export file import** or a **small companion app** before scraping.

