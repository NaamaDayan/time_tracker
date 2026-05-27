#!/usr/bin/env bash
# Optional @reboot helper — start Postgres + Dawarich after the machine boots.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose up -d db dawarich_db dawarich_redis dawarich_app dawarich_sidekiq
