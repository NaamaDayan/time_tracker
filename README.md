# Time Tracker (MVP)

Personal time and habit tracker powered by **ActivityWatch** (laptop time). Week timeline + automatic habit scores.

## Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Node.js 20+
- [ActivityWatch](https://activitywatch.net/) installed and running (grants Accessibility permissions on macOS)

## Quick start

### 1. Environment

```bash
cp .env.example .env
# Edit .env: optionally set USER_TIMEZONE, ACTIVITYWATCH_BASE_URL
```

### 2. Database

```bash
docker compose up -d db
```

### 3. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Use `--host 0.0.0.0` so your phone can reach the API over Wi‑Fi (not only `localhost` on the Mac).

### 4. Sync ActivityWatch data

```bash
# From repo root (with venv active and PYTHONPATH=backend)
cd backend && PYTHONPATH=. python -m app.connectors.activitywatch sync --since 7d

# Or use the helper script
chmod +x scripts/sync_all.sh
./scripts/sync_all.sh 7d
```

### 5. Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local   # or symlink; needs BACKEND_URL, API_KEY, FRONTEND_URL=http://localhost:3001
npm run dev
```

Open [http://localhost:3001](http://localhost:3001) (Time Tracker UI; Dawarich stays on port **3000**). Use **Sync ActivityWatch** to pull the latest week.

API docs (dev): [http://localhost:8000/docs](http://localhost:8000/docs) — requires `X-API-Key` header.

## Manual test checklist

- `docker compose up -d db` — Postgres healthy
- `alembic upgrade head` — migrations apply on fresh DB
- `pytest` in `backend/` — all tests pass (no network)
- `python -m app.connectors.activitywatch sync --since 7d` — returns counts when ActivityWatch is running
- `GET /api/v1/timeline` — segments for current week
- `GET /api/v1/habits/weekly?week=YYYY-Www` — three habit goals with scores
- Frontend week grid shows colored work blocks after sync
- Empty state when no data; error banner when API down
- Habit dots reflect daily scores (green / amber / red)

## ActivityWatch Desktop (Mac usage)

Desktop app usage is tracked by **ActivityWatch** running locally on your Mac. The backend polls the AW REST API (`http://127.0.0.1:5600`) for `aw-watcher-window` events (active app + window title) and optionally filters by `aw-watcher-afk` (idle detection).

1. Install [ActivityWatch](https://activitywatch.net/downloads/) and grant **Accessibility** permissions on macOS.
2. Ensure ActivityWatch is running (tray icon visible).
3. Sync: `python -m app.connectors.activitywatch sync --since 7d`

Classification: all desktop time defaults to `work`; app-name rules in `activitywatch_desktop.yaml` override (e.g. Slack -> communication, Spotify -> music/podcast).

Status: `GET /api/v1/integrations/activitywatch/status`

## Habit goals (MVP)


| Slug                  | Rule                       |
| --------------------- | -------------------------- |
| `weekday_work_target` | Mon–Fri: ≥ 6h work per day |
| `weekend_work_cap`    | Sat–Sun: ≤ 2h work per day |
| `weekly_work_total`   | ≥ 40h work per ISO week    |


## Samsung Health (watch via phone)

Health data is read from **Samsung Health** on your Android phone (Galaxy Watch syncs there), not from the watch API directly.

1. Run backend with `API_KEY` set (see `.env`) and `**--host 0.0.0.0`** (see step 3 above).
2. Open `companion-android/` in Android Studio, add `samsung-health-data-api.aar` to `app/libs/` (see [companion-android/README.md](companion-android/README.md)).
3. Phone and Mac on the **same Wi‑Fi**. Backend URL must use your Mac’s IP on that network (e.g. `http://192.168.1.42:8000` — same subnet as the phone, not `localhost`).
4. **Connect & grant permissions** → allow Sleep, Exercise, Steps → **Sync now**.
5. **Refresh the web calendar** (reload the page or click **Sync** on the site) — the phone upload does not auto-refresh the browser.
6. Sleep and workouts appear on the week **Calendar** (purple/indigo sleep blocks, green border for health events).

**Automatic sync:** After **Save settings**, the Android app also syncs about every **12 hours** in the background (if permissions stay granted). For fresh data, use **Sync now** on the phone.

Status: `GET /api/v1/integrations/samsung/status`

## Activity Watch (phone apps)

Per-app usage is read from **Activity Watch** on your Samsung phone (Usage Access), then classified by app name (WhatsApp → communication, Spotify → music/podcast, etc.). See [companion-android/README.md](companion-android/README.md).

1. Install [Activity Watch for Android](https://play.google.com/store/apps/details?id=net.activitywatch.android) and grant **Usage Access**.
2. Same backend + companion setup as Samsung Health (`--host 0.0.0.0`, LAN IP, API key).
3. **Open Activity Watch on the phone** (its API only runs while that app has started). In the companion: **Open Activity Watch app** → wait a few seconds → **Sync Activity Watch**.
4. Reload the web app — **Calendar** (gap-merged windows, 5 min), **Pie chart** (overlap totals), and **Net** (additive totals) all include phone data.

**Automatic sync:** Every ~12 hours via WorkManager when settings are saved.

Status: `GET /api/v1/integrations/activitywatch/status`

**Limits:** Android AW does not sync to desktop automatically; background Spotify is only counted when AW records foreground usage. Phone `work` overlaps with desktop ActivityWatch laptop time — pie chart picks one winner per instant.

## Dawarich (GPS / location store)

[Dawarich](https://dawarich.app/) stores raw GPS points and detects place visits. The Android companion uploads points; the backend pulls visits daily.

### Start Dawarich

```bash
# From repo root (not backend/). On Apple Silicon this uses imresamu/postgis automatically.
docker compose up -d dawarich_db dawarich_redis dawarich_app dawarich_sidekiq
# First boot may take 1–2 minutes for dawarich_app healthcheck
curl -s http://localhost:3000/api/v1/health
```

**Apple Silicon error** (`no matching manifest for linux/arm64` on `postgis/postgis`): the compose file already defaults to `imresamu/postgis:17-3.5-alpine`. Pull again after `git pull`. On Intel Linux you can set `DAWARICH_DB_IMAGE=postgis/postgis:17-3.5-alpine` in `.env` if you prefer.

### Log in (first time)

Self-hosted Dawarich on Docker is **free** — you are not missing a “paid” account.

Our compose uses `RAILS_ENV=production`, so **no default user is created automatically** (upstream docs that mention `admin@dawarich.app` / `safepassword` are often wrong for production). Create your own admin once:

```bash
cd /path/to/time_tracker_cursor
docker exec -it dawarich_app bin/rails console
```

In the Rails console (replace email/password with yours; password ≥ 6 characters):

```ruby
User.create!(email: "you@example.com", password: "your-password", password_confirmation: "your-password", admin: true)
exit
```

Then open **[http://localhost:3000](http://localhost:3000)** and sign in with that email and password.

**Optional:** On some image versions the seeded user is `**user@domain.com`** / `**password**` — try that before creating a user. Check existing users: `User.pluck(:email)` in the console.

### Get your Dawarich API key (simple)

1. Open **[http://localhost:3000](http://localhost:3000)** and log in (see above).
2. Click your **profile / account** (top-right avatar or menu).
3. Open **Settings** (or **API** / **API key** section — wording varies slightly by version).
4. Copy the **API key** (or click **Generate** if empty, then copy).
5. Paste it into your project `.env`:
  ```bash
   DAWARICH_API_KEY=paste-the-key-here
   DAWARICH_BASE_URL=http://localhost:3000
  ```
6. Use the **same key** in the Android companion under **Dawarich API key** (for uploading GPS points).

Set `USER_TIMEZONE` and `DAWARICH_TIME_ZONE` to the same value (e.g. `Asia/Jerusalem`).

Verify visits API (empty list is OK):

```bash
curl -s "http://localhost:3000/api/v1/visits?api_key=$DAWARICH_API_KEY&start_at=2026-01-01T00:00:00Z&end_at=2026-01-02T00:00:00Z"
```

See [docker/dawarich.env.example](docker/dawarich.env.example) for Dawarich-only Docker variables. On ARM64, see [docker-compose.override.yml.example](docker-compose.override.yml.example).

### Location ingest (geofence + daily visits)

- Phone: geofence ENTER/EXIT → `POST /api/v1/integrations/location/geofence` (immediate).
- Phone: GPS points → Dawarich `POST /api/v1/owntracks/points?api_key=...` (batched on Wi‑Fi).
- Backend: daily `sync_dawarich` at `DAWARICH_SYNC_HOUR` in `USER_TIMEZONE`, or manual:

```bash
cd backend && PYTHONPATH=. python -m app.connectors.dawarich.cli sync --since 2d
```

Status: `GET /api/v1/integrations/location/status`

## Project layout

See [CURSOR.md](CURSOR.md) for architecture and v0.2 roadmap (Google Calendar, etc.).

## Local home server (always-on + phone over Tailscale)

Step-by-step plan for running everything on a home computer with **automatic phone sync on Wi‑Fi or cellular** (no AWS): [docs/LOCAL_HOME_SERVER.md](docs/LOCAL_HOME_SERVER.md).

## Cron (optional)

```bash
0 */6 * * * /path/to/time_tracker_cursor/scripts/sync_all.sh 7d
```





docker stop $(docker ps -q) 