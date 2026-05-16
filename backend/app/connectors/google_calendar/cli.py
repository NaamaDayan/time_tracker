import argparse
import logging

from app.connectors.google_calendar.sync import sync_google_calendar
from app.database import SessionLocal

logging.basicConfig(level=logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Google Calendar events")
    parser.parse_args()
    db = SessionLocal()
    try:
        result = sync_google_calendar(db)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
