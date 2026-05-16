"""CLI for window aggregation backfill."""

import argparse
from datetime import datetime, timezone

from app.database import SessionLocal
from app.pipeline.windows.service import backfill_all_windows


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Activity window aggregation")
    sub = parser.add_subparsers(dest="command", required=True)

    backfill = sub.add_parser("backfill", help="Rebuild all activity windows from segments")
    backfill.add_argument("--from", dest="from_", metavar="ISO", help="Limit segment start (ISO datetime)")
    backfill.add_argument("--to", metavar="ISO", help="Limit segment end (ISO datetime)")

    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.command == "backfill":
            from_ = _parse_iso(args.from_)
            to = _parse_iso(args.to)
            count = backfill_all_windows(db, from_=from_, to=to)
            print(f"Wrote {count} activity window(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
