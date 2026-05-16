# Time Tracker (MVP)

Personal time and habit tracker powered by **Clockify** (laptop time). Week timeline + automatic habit scores.

## Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Node.js 20+
- [Clockify](https://clockify.me) account with API key ([Profile → API](https://app.clockify.me/user/settings))

## Quick start

### 1. Environment

```bash
cp .env.example .env
# Edit .env: set CLOCKIFY_API_KEY, optionally USER_TIMEZONE
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
uvicorn app.main:app --reload
```

### 4. Sync Clockify data

```bash
# From repo root (with venv active and PYTHONPATH=backend)
cd backend && PYTHONPATH=. python -m app.connectors.clockify sync --since 7d

# Or use the helper script
chmod +x scripts/sync_all.sh
./scripts/sync_all.sh 7d
```

### 5. Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local   # or symlink; needs BACKEND_URL and API_KEY
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Use **Sync Clockify** to pull the latest week.

API docs (dev): [http://localhost:8000/docs](http://localhost:8000/docs) — requires `X-API-Key` header.

## Manual test checklist

- [ ] `docker compose up -d db` — Postgres healthy
- [ ] `alembic upgrade head` — migrations apply on fresh DB
- [ ] `pytest` in `backend/` — all tests pass (no network)
- [ ] `python -m app.connectors.clockify sync --since 7d` — returns counts with valid API key
- [ ] `GET /api/v1/timeline` — segments for current week
- [ ] `GET /api/v1/habits/weekly?week=YYYY-Www` — three habit goals with scores
- [ ] Frontend week grid shows colored work blocks after sync
- [ ] Empty state when no data; error banner when API down
- [ ] Habit dots reflect daily scores (green / amber / red)

## Habit goals (MVP)

| Slug | Rule |
|------|------|
| `weekday_work_target` | Mon–Fri: ≥ 6h work per day |
| `weekend_work_cap` | Sat–Sun: ≤ 2h work per day |
| `weekly_work_total` | ≥ 40h work per ISO week |

## Project layout

See [CURSOR.md](CURSOR.md) for architecture and v0.2 roadmap (Google Calendar, etc.).

## Cron (optional)

```bash
0 */6 * * * /path/to/time_tracker_cursor/scripts/sync_all.sh 7d
```
