#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
export PYTHONPATH=.
python -c "
from app.database import SessionLocal
from app.connectors.sync_all import sync_all_sources
import json
result = sync_all_sources(SessionLocal(), since='${1:-7d}')
print(json.dumps(result, indent=2))
"
# Dawarich is included in sync_all_sources when DAWARICH_API_KEY is set in .env
