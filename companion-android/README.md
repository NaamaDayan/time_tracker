# Time Tracker — Android companion

Reads **Samsung Health** (watch data syncs here) and **Activity Watch** (per-app phone usage) on your phone, then POSTs batches to your Time Tracker backend.

## Prerequisites

- Android 10+ **physical device** (emulator not supported for Samsung Health)
- Backend reachable from the phone — **same Wi‑Fi** (`http://192.168.x.x:8000`) or **Tailscale** (`http://100.x.x.x:8000`) for sync away from home. See [docs/LOCAL_HOME_SERVER.md](../docs/LOCAL_HOME_SERVER.md).
- Backend running with `API_KEY` and `uvicorn --host 0.0.0.0 --port 8000`

### Samsung Health

- Samsung Health **6.30.2+** installed
- Samsung developer account; **Developer Mode** in Samsung Health (Settings → About)
- Samsung Health Data SDK `.aar` in `app/libs/` (see [Samsung Health Data SDK](https://developer.samsung.com/health/data/guide/introduction.html))

### Activity Watch

- [Activity Watch for Android](https://play.google.com/store/apps/details?id=net.activitywatch.android) installed
- **Usage Access** granted to Activity Watch (Android Settings → Apps → Special access)
- Activity Watch app open or running in background when you sync (local API at `http://127.0.0.1:5600`)

## Setup

1. Open `companion-android/` in Android Studio.
2. Copy `samsung-health-data-api.aar` → `app/libs/` (for health sync only).
3. Set **Backend URL** — e.g. `http://192.168.1.10:8000` (your machine’s LAN IP, not `localhost`)
4. Set **API key** — same as `API_KEY` in `.env`
5. Tap **Save settings** (enables 12h background sync for both sources).

## Samsung Health sync

1. **Connect & grant permissions** → allow Sleep, Exercise, Steps.
2. **Sync Samsung Health** — uploads last 14 days.

`POST /api/v1/integrations/samsung/ingest`

## Activity Watch sync

Activity Watch runs a **local server only while its app is open** (port 5600 on the phone). The companion talks to `127.0.0.1` on the device — not your Mac.

1. Install Activity Watch and grant **Usage Access**.
2. Tap **Open Activity Watch app** and leave the app running (or switch away after it loads).
3. Optional: on the phone browser, open `http://127.0.0.1:5600/api/0/info` — you should see JSON. If not, AW’s server is not up.
4. Tap **Sync Activity Watch** in the companion (retries for ~4s while the server starts).

If sync still fails: disable battery optimization for Activity Watch, complete AW onboarding, then open AW again before syncing.

`POST /api/v1/integrations/activitywatch/ingest`

App usage is classified on the server (`activitywatch.yaml`): e.g. WhatsApp → communication, Spotify → music/podcast, unmatched apps → phone usage.

## Web UI

After either sync, **reload** the web app (http://localhost:3001):

- **Calendar** — gap-merged windows (`ACTIVITY_MERGE_GAP_MINUTES`, default 5)
- **Pie chart** — overlap winner per instant
- **Net** — additive durations (can exceed 24h when overlapping)

## Periodic sync

- `HealthSyncWorker` — Samsung Health every 12h
- `ActivityWatchSyncWorker` — Activity Watch every 12h

Use manual sync buttons for fresh data.

## Location (GPS + geofences)

Tracks place visits using **Activity Recognition** (STILL vs MOVING), **hardware geofences** for named zones, and **fused location** (5 min while moving). Points upload to **Dawarich**; geofence events upload to the Time Tracker backend immediately.

1. Start Dawarich: `docker compose up -d dawarich_app` (see root [README.md](../README.md)).
2. In Dawarich UI → User settings → copy **API key**.
3. In the companion: set **Dawarich URL** (LAN IP, e.g. `http://192.168.1.10:3000`), **Dawarich API key**, backend URL + API key.
4. Edit zone coordinates in `app/src/main/assets/geofence_zones.json` (home, office, gym, parents).
5. Tap **Location permissions** until all are granted (fine + background location + activity recognition + **Notifications** on Android 13+).
6. Tap **Disable battery optimization** (required on Samsung).
7. Tap **Start location tracking** — foreground notification stays on while enabled.

If the app closes when starting tracking, check **Logcat** filter `LocationTrackingService` — usually missing **Notifications** permission or location permission denied for the foreground service.

**Upload paths**

| Data | Target |
|------|--------|
| GPS points (batched every 15 min; Wi‑Fi by default) | `POST {dawarich}/api/v1/owntracks/points?api_key=...` |

Enable **Upload location on mobile data** in the app for GPS upload over Tailscale on cellular.
| Geofence ENTER/EXIT | `POST {backend}/api/v1/integrations/location/geofence` |

Backend classifies zones via `location_zones.yaml`; daily Dawarich visit pull runs at 02:00 (`USER_TIMEZONE`).

## Manual test checklist

- [ ] Activity Watch Usage Access granted
- [ ] AW reachable: companion shows bucket count / sessions on sync (not “not reachable”)
- [ ] `GET /api/v1/integrations/activitywatch/status` shows `connected: true` after ingest
- [ ] Calendar shows phone blocks (e.g. communication merged if gap ≤ 5 min)
- [ ] Pie chart includes phone types; slices + unattributed ≈ 100% of range
- [ ] Net view shows additive phone_usage / communication totals
- [ ] Location: geofence ENTER/EXIT in backend logs; points on Dawarich map
- [ ] `GET /api/v1/integrations/location/status` shows last geofence event
