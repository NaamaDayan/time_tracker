# Local home server deployment plan

Run the full Time Tracker stack on an **always-on computer at home**. Your phone **pushes data automatically** in the background (no manual sync buttons after initial setup), including when you are **not on home Wi‑Fi**, by reaching the server over **Tailscale** (private VPN).

This guide assumes:

- **Home server**: Mac mini, Intel/ARM Linux box, NUC, or NAS with Docker (4 GB+ RAM recommended if you run Dawarich on the same machine).
- **Phone**: Samsung Android with the companion app (Samsung Health, Activity Watch, location).
- **Laptop Mac** (optional, intermittent): ActivityWatch Desktop — syncs when the Mac is on.

---

## Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│  Always-on home computer                                          │
│  • Docker: Postgres (time_tracker) + Dawarich (app/db/redis)     │
│  • FastAPI backend (:8000) — ingest + scheduler                  │
│  • Next.js frontend (:3001) — week calendar UI                   │
│  • Tailscale — stable IP for phone on Wi‑Fi or cellular          │
└────────────────────────────▲─────────────────────────────────────┘
                             │  http://100.x.x.x:8000  (Tailscale)
┌────────────────────────────┴─────────────────────────────────────┐
│  Phone (background, no buttons after setup)                       │
│  • Samsung Health      → POST /integrations/samsung/ingest (~12h) │
│  • Activity Watch      → POST /integrations/activitywatch (~12h)│
│  • Geofence ENTER/EXIT → POST /integrations/location/geofence   │
│  • GPS points          → POST Dawarich /owntracks/points (~15m) │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Mac laptop (when powered on)                                     │
│  • ActivityWatch Desktop → python sync → home Postgres             │
└──────────────────────────────────────────────────────────────────┘
```

**Why Tailscale (not only LAN IP)?**  
The companion README defaults to `http://192.168.x.x:8000`, which only works on the same Wi‑Fi. On **mobile data**, that address is unreachable. Tailscale gives both devices a `100.x.x.x` address on a private network, so background workers keep working away from home.

**What already runs automatically (after “Save settings” on the phone):**

| Source | Mechanism | Interval |
|--------|-----------|----------|
| Samsung Health | `HealthSyncWorker` | ~12 hours |
| Activity Watch | `ActivityWatchSyncWorker` | ~12 hours |
| GPS → Dawarich | `DawarichUploadWorker` | ~15 minutes (Wi‑Fi only by default — see [Phase 8](#phase-8-phone-off-wi-fi-cellular)) |
| Geofence | Immediate on ENTER/EXIT | Event-driven |
| Dawarich visits | APScheduler on backend | Daily (`DAWARICH_SYNC_HOUR`) |
| Google Calendar | Server pull (after OAuth) | Add cron or extend scheduler (see Phase 6) |

---

## Phase 0 — Choose and prepare the home computer

### Hardware

| Component | Minimum | Recommended |
|-----------|---------|---------------|
| RAM | 4 GB (Dawarich + Postgres tight) | 8 GB |
| Disk | 40 GB free | 100 GB+ (location history grows) |
| OS | macOS, Ubuntu 22.04+, or similar | Same |

The machine should:

- Stay powered on (or wake on LAN if you accept occasional gaps).
- Use **Ethernet** if possible (more stable than Wi‑Fi for a server).
- Have **Docker Desktop** (Mac) or **Docker Engine** (Linux).

### Accounts to create beforehand

- [Tailscale](https://tailscale.com) — free personal plan is enough.
- [Google Cloud Console](https://console.cloud.google.com) — for Calendar OAuth (optional).
- [ActivityWatch](https://activitywatch.net/) — desktop app on your Mac (optional).
- Samsung developer account — for Health SDK `.aar` (phone only).

---

## Phase 1 — Install base software on the home computer

### 1.1 Docker

**macOS:** Install [Docker Desktop](https://www.docker.com/products/docker-desktop/). Enable “Start Docker Desktop when you log in”.

**Linux (Ubuntu example):**

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker "$USER"
# Log out and back in so docker runs without sudo
```

### 1.2 Python 3.12 + Node 20

**macOS (Homebrew):**

```bash
brew install python@3.12 node@20
```

**Linux:**

```bash
sudo apt install -y python3.12 python3.12-venv nodejs npm
# Or use nvm/fnm for Node 20
```

### 1.3 Tailscale on the home computer

```bash
# macOS: brew install --cask tailscale   OR download from tailscale.com
# Linux:
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Note the machine’s Tailscale IP:

```bash
tailscale ip -4
# Example: 100.64.0.12
```

You will use this as `HOME_TS_IP` below.

### 1.4 Clone the project

```bash
git clone <your-repo-url> ~/time_tracker_cursor
cd ~/time_tracker_cursor
```

---

## Phase 2 — Configure environment (`.env`)

```bash
cp .env.example .env
```

Edit `.env` for the **home server** (replace placeholders):

```bash
# Database — Docker Postgres on the same machine
DATABASE_URL=postgresql+psycopg://tracker:tracker@localhost:5432/time_tracker
USER_TIMEZONE=Asia/Jerusalem

# Strong secret for phone + API access
API_KEY=<generate-a-long-random-string>

# ActivityWatch Desktop — only used when you run sync FROM a Mac with the AW app
ACTIVITYWATCH_BASE_URL=http://127.0.0.1:5600
ACTIVITYWATCH_POLL_ENABLED=true

# Dawarich — backend pulls visits; phone uploads GPS points
DAWARICH_BASE_URL=http://100.64.0.12:3000
DAWARICH_API_KEY=<from-dawarich-ui-after-phase-3>
DAWARICH_SYNC_ENABLED=true
DAWARICH_SYNC_HOUR=2
LOCATION_GEOFENCE_ENABLED=true
DAWARICH_TIME_ZONE=Asia/Jerusalem

# Google Calendar (optional)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://100.64.0.12:8000/api/v1/integrations/google/callback
FRONTEND_URL=http://100.64.0.12:3001

# UI proxy
BACKEND_URL=http://100.64.0.12:8000
```

**Important:** Use your real `HOME_TS_IP` (`100.x.x.x`) in URLs the phone and browser will use over Tailscale. Keep `localhost` only inside the server for processes that bind locally.

Generate an API key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Phase 3 — Start databases and Dawarich (Docker)

From the repo root:

```bash
docker compose up -d db
docker compose up -d dawarich_db dawarich_redis dawarich_app dawarich_sidekiq
```

Wait until healthy:

```bash
docker compose ps
curl -s http://localhost:3000/api/v1/health
```

### 3.1 Create Dawarich admin user (first time only)

```bash
docker exec -it dawarich_app bin/rails console
```

In the Rails console:

```ruby
User.create!(email: "you@example.com", password: "your-secure-password",
             password_confirmation: "your-secure-password", admin: true)
exit
```

### 3.2 Get Dawarich API key

1. On a machine with Tailscale, open `http://100.64.0.12:3000` (your `HOME_TS_IP`).
2. Log in → Settings / API → copy API key.
3. Paste into `.env` as `DAWARICH_API_KEY`.
4. Restart nothing yet — backend reads `.env` on start.

### 3.3 Allow Dawarich to accept Tailscale host (if needed)

If Dawarich rejects requests, add your Tailscale IP to `DAWARICH_APPLICATION_HOSTS` in `.env` and recreate the app container:

```bash
# .env
DAWARICH_APPLICATION_HOSTS=localhost,127.0.0.1,::1,100.64.0.12
docker compose up -d dawarich_app
```

---

## Phase 4 — Backend API (migrations + always-on process)

```bash
cd ~/time_tracker_cursor/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
```

Test manually once:

```bash
cd ~/time_tracker_cursor/backend
source .venv/bin/activate
export PYTHONPATH=.
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

From another device on Tailscale:

```bash
curl -s -H "X-API-Key: YOUR_API_KEY" http://100.64.0.12:8000/api/v1/integrations/samsung/status
```

Stop the test server (Ctrl+C) and install a **service** so it survives reboots.

### 4.1 macOS — `launchd` (home server is a Mac)

Copy and edit the example plist (set paths and API key):

```bash
cp docs/examples/com.timetracker.api.plist ~/Library/LaunchAgents/
# Edit: WorkingDirectory, venv python path, EnvironmentVariables
launchctl load ~/Library/LaunchAgents/com.timetracker.api.plist
launchctl list | grep timetracker
```

See [docs/examples/com.timetracker.api.plist](examples/com.timetracker.api.plist).

### 4.2 Linux — `systemd`

```bash
sudo cp docs/examples/time-tracker-api.service /etc/systemd/system/
# Edit paths in the file
sudo systemctl daemon-reload
sudo systemctl enable --now time-tracker-api
sudo systemctl status time-tracker-api
```

See [docs/examples/time-tracker-api.service](examples/time-tracker-api.service).

### 4.3 Docker auto-restart

Ensure database containers restart after reboot (repo `docker-compose.yml` uses `restart: unless-stopped` on `db` and Dawarich services). After OS login, start Docker, then:

```bash
cd ~/time_tracker_cursor && docker compose up -d db dawarich_db dawarich_redis dawarich_app dawarich_sidekiq
```

Optional: add a crontab `@reboot` line for the above if Docker does not auto-start stacks.

---

## Phase 5 — Frontend (week UI)

```bash
cd ~/time_tracker_cursor/frontend
npm install
cp ../.env.example .env.local
```

Edit `frontend/.env.local`:

```bash
BACKEND_URL=http://100.64.0.12:8000
API_KEY=<same-as-root-.env>
FRONTEND_URL=http://100.64.0.12:3001
```

**Development (simplest):**

```bash
npm run dev
# Binds port 3001 — use launchd/systemd similar to API for production
```

**Production build (optional):**

```bash
npm run build && npm run start
```

Open the UI from any Tailscale device: `http://100.64.0.12:3001`.

---

## Phase 6 — Scheduled server-side sync (no buttons)

The backend already schedules **Dawarich visit pull** daily when `DAWARICH_SYNC_ENABLED=true` (`scheduler.py`).

### 6.1 Google Calendar (optional)

1. Set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` in `.env` (Tailscale URL).
2. In [Google Cloud Console](https://console.cloud.google.com), add the redirect URI exactly.
3. On a browser (Tailscale): open  
   `http://100.64.0.12:8000/api/v1/integrations/google/connect`  
   (or use the link from your UI) and complete OAuth once.
4. Add a cron job on the home server for calendar + full pull:

```bash
crontab -e
```

```cron
# Every 6 hours: ActivityWatch Desktop (if run on THIS Mac), Calendar, Dawarich
0 */6 * * * cd /home/YOU/time_tracker_cursor && ./scripts/sync_all.sh 7d >> /var/log/time-tracker-sync.log 2>&1
```

`sync_all.sh` runs ActivityWatch Desktop + Google Calendar + Dawarich when configured.

> **Note:** Google Calendar sync is not yet in APScheduler — cron is the simple approach. Extending `scheduler.py` is an optional code improvement.

---

## Phase 7 — Phone setup (one-time + background forever)

### 7.1 Install Tailscale on the phone

- Install Tailscale from Play Store; log in to the **same tailnet** as the home server.
- Ensure the phone shows as connected in the Tailscale admin console.

### 7.2 Build / install companion app

Follow [companion-android/README.md](../companion-android/README.md):

- Physical Samsung device, Health SDK `.aar` in `app/libs/`.
- Install debug/release APK.

### 7.3 Configure companion URLs (Tailscale, not LAN)

In the companion app:

| Field | Value |
|-------|--------|
| **Backend URL** | `http://100.64.0.12:8000` |
| **API key** | Same as `API_KEY` in `.env` |
| **Dawarich URL** | `http://100.64.0.12:3000` |
| **Dawarich API key** | Same as `DAWARICH_API_KEY` |

Tap **Save settings** — this registers WorkManager jobs (12h health/AW, 15m location upload).

### 7.4 Samsung Health (one-time permissions)

1. **Connect & grant permissions** (Sleep, Exercise, Steps).
2. Optional manual **Sync Samsung Health** to verify; afterward background sync runs every ~12h.

### 7.5 Activity Watch

1. Install Activity Watch; grant **Usage Access**.
2. Open Activity Watch at least once so its local API starts (`127.0.0.1:5600` on the phone).
3. Optional manual sync to verify; background runs ~12h (AW must occasionally run — Android limitation).

### 7.6 Location tracking (one-time)

1. Edit zones in `companion-android/app/src/main/assets/geofence_zones.json` (rebuild app if you change coordinates).
2. Grant location + background location + activity recognition + notifications.
3. **Disable battery optimization** for the companion (critical on Samsung).
4. Tap **Start location tracking** once (foreground notification stays on).

Geofence events POST immediately to the backend when the network is up.

### 7.7 Verify from the home server

```bash
curl -s -H "X-API-Key: YOUR_KEY" http://localhost:8000/api/v1/integrations/samsung/status
curl -s -H "X-API-Key: YOUR_KEY" http://localhost:8000/api/v1/integrations/activitywatch/status
curl -s -H "X-API-Key: YOUR_KEY" http://localhost:8000/api/v1/integrations/location/status
```

Reload `http://100.64.0.12:3001` after the first successful syncs.

---

## Phase 8 — Phone off Wi‑Fi (cellular)

| Data | On cellular (Tailscale) | Notes |
|------|-------------------------|--------|
| Samsung Health | Works | `HealthSyncWorker` has no Wi‑Fi-only gate |
| Activity Watch | Works | Same |
| Geofence | Works if online at event time | No offline queue — failed upload is lost |
| GPS → Dawarich | **Blocked by default** | `DawarichUploadWorker` only uploads on Wi‑Fi; points stay buffered on phone |

**To upload GPS on mobile data:** enable **Upload location on mobile data** in the companion app (Settings), or keep default and points flush when you reconnect to Wi‑Fi.

**Tailscale on cellular:** Works on mobile data; no port forwarding on your router required.

**Android battery:** Disable optimization for: companion app, Activity Watch, Samsung Health, Tailscale.

---

## Phase 9 — ActivityWatch Desktop on your Mac laptop (when it is on)

ActivityWatch runs locally on your Mac and exposes a REST API at `http://127.0.0.1:5600`. The sync script polls this API for window/AFK events and writes them to the home Postgres (reachable via Tailscale).

On the **Mac where ActivityWatch Desktop runs**, point sync at the **home Postgres**:

```bash
# ~/time_tracker_cursor/backend — on the Mac
source .venv/bin/activate
export PYTHONPATH=.
export DATABASE_URL=postgresql+psycopg://tracker:tracker@100.64.0.12:5432/time_tracker
python -m app.connectors.activitywatch sync --since 7d
```

### 9.1 Automate with `launchd` or cron on the Mac

Create a launchd plist (or cron job) that runs the sync command every 6 hours and at login. Safe to miss runs when the Mac sleeps (`--since 7d` is idempotent).

---

## Phase 10 — Auto-start after power loss / reboot

Use this checklist:

| Layer | Action |
|-------|--------|
| OS | Enable auto-login or headless boot; disable sleep on the server (macOS: Energy Saver; Linux: `systemctl mask sleep`) |
| Docker | Start on boot; `docker compose up -d` for `db` + Dawarich |
| Backend API | `launchd` / `systemd` `enable` |
| Frontend | `launchd` / `systemd` or `npm run start` in a service |
| Tailscale | Install with “start on boot” |
| Mac ActivityWatch | `launchd` on the laptop |
| Phone | No action — WorkManager resumes after reboot |

### Smoke test after reboot

1. `curl http://localhost:8000/` — API up.
2. `docker compose ps` — all healthy.
3. `tailscale status` — phone and server connected.
4. Wait 15+ minutes or force a test sync from the phone; check integration status endpoints.

---

## Phase 11 — Security checklist (local but exposed to tailnet)

- [ ] Change default Postgres password in `docker-compose.yml` for anything beyond pure LAN lab use.
- [ ] Use a long random `API_KEY`; never commit `.env`.
- [ ] Restrict Tailscale ACLs to your own devices if you share the tailnet.
- [ ] Do not port-forward `:8000` / `:3000` to the public internet without HTTPS and auth hardening.
- [ ] Back up Docker volumes (`pgdata`, `dawarich_db_data`) periodically.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| Phone sync fails away from home | LAN URL in companion | Switch Backend/Dawarich URLs to `http://100.x.x.x:...` |
| Samsung sync never runs | Battery optimization | Disable for companion; confirm Save settings |
| AW “not reachable” | AW app not started | Open Activity Watch; retry |
| No GPS on Dawarich map | Wi‑Fi-only upload | Enable mobile-data upload in companion or wait for Wi‑Fi |
| Geofence missing | Offline at ENTER/EXIT | Expected until offline queue is added; rely on Dawarich visits |
| Calendar empty | OAuth not done | Complete connect flow; run `sync_all.sh` |
| AW Desktop empty | Mac asleep | Normal; sync runs when Mac is on |
| Dawarich 403 / blocked host | `APPLICATION_HOSTS` | Add Tailscale IP to `DAWARICH_APPLICATION_HOSTS` |

---

## Optional improvements (later)

- Containerize FastAPI + Next.js in `docker-compose` for a single `docker compose up`.
- Add Google Calendar to `scheduler.py` (same as Dawarich).
- Offline queue for geofence events in the companion.
- HTTPS via Tailscale Serve or Caddy on the home server.
- Backups: `pg_dump` cron to an external drive or S3.

---

## Quick reference — URLs on your tailnet

Replace `100.64.0.12` with your `HOME_TS_IP`:

| Service | URL |
|---------|-----|
| API docs | `http://100.64.0.12:8000/docs` |
| Web UI | `http://100.64.0.12:3001` |
| Dawarich | `http://100.64.0.12:3000` |
| Samsung status | `GET /api/v1/integrations/samsung/status` |
| AW status | `GET /api/v1/integrations/activitywatch/status` |
| Location status | `GET /api/v1/integrations/location/status` |

All API calls require header: `X-API-Key: <your API_KEY>`.
