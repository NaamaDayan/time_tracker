import argparse
from datetime import datetime, timedelta, timezone

from app.connectors.utils import parse_since
from app.connectors.dawarich.sync import sync_dawarich
from app.database import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Dawarich visits")
    parser.add_argument("--since", default="1d", help="e.g. 7d, 2026-05-01")
    parser.add_argument("--until", default=None, help="ISO datetime end (default: now)")
    args = parser.parse_args()

    since = parse_since(args.since)
    until = (
        datetime.fromisoformat(args.until.replace("Z", "+00:00"))
        if args.until
        else datetime.now(timezone.utc)
    )
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)

    with SessionLocal() as db:
        result = sync_dawarich(db, since=since, until=until)
    print(result)


if __name__ == "__main__":
    main()
