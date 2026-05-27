import argparse
import sys
from datetime import datetime, timezone

from app.connectors.activitywatch.desktop_sync import sync_activitywatch_desktop
from app.database import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync ActivityWatch Desktop events")
    parser.add_argument("command", choices=["sync"], nargs="?", default="sync")
    parser.add_argument("--since", default="7d", help="e.g. 7d, 14d, 2w")
    parser.add_argument("--from", dest="from_dt", help="ISO8601 start")
    parser.add_argument("--to", dest="to_dt", help="ISO8601 end")
    args = parser.parse_args()

    start = None
    end = None
    if args.from_dt:
        start = datetime.fromisoformat(args.from_dt.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
    if args.to_dt:
        end = datetime.fromisoformat(args.to_dt.replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

    db = SessionLocal()
    try:
        result = sync_activitywatch_desktop(db, since=args.since, start=start, end=end)
        print(result)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
