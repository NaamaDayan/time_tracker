# Time Tracker — Samsung Health companion

Minimal Android app that reads **Samsung Health** (watch data syncs here) via the [Samsung Health Data SDK](https://developer.samsung.com/health/data/guide/introduction.html) and POSTs batches to your Time Tracker backend.

## Prerequisites

- Android 10+ **physical device** (emulator not supported)
- Samsung Health **6.30.2+** installed
- Samsung developer account; enable **Developer Mode** in Samsung Health (Settings → About)
- Download the Samsung Health Data SDK `.aar` from Samsung Developer and place it in `app/libs/` (e.g. `samsung-health-data-api-1.1.0.aar`; any `*.aar` in that folder is picked up by Gradle)

## Setup

1. Open `companion-android/` in Android Studio.
2. Copy `samsung-health-data-api.aar` → `app/libs/`.
3. In the app, set:
   - **Backend URL** — e.g. `http://192.168.1.10:8000` (your machine’s LAN IP, not `localhost`)
   - **API key** — same as `API_KEY` in your `.env`
4. Tap **Connect & grant permissions** → Samsung Health opens a popup → allow **Sleep**, **Exercise**, and **Steps** (all three).
5. If no popup appears, enable **Developer Mode** in Samsung Health (Settings → About Samsung Health).
6. Tap **Sync now** to upload the last 14 days.

## Backend endpoint

`POST /api/v1/integrations/samsung/ingest` with header `X-API-Key` and JSON body (see plan / `backend/tests/fixtures/samsung_health_ingest.json`).

## Periodic sync

`HealthSyncWorker` runs every 12 hours via WorkManager when backend URL and API key are configured.

## Spike checklist

- [ ] Samsung Health Developer Mode on
- [ ] App connects without resolution error
- [ ] Sleep session appears on week calendar after sync
- [ ] Exercise session appears on calendar
- [ ] Raw rows in `raw_events` with `source = samsung_health`
