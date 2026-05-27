import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.connectors.dawarich.sync import sync_dawarich_yesterday
from app.database import SessionLocal

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_dawarich_sync() -> None:
    settings = get_settings()
    if not settings.dawarich_sync_enabled or not settings.dawarich_api_key:
        logger.info("Dawarich scheduled sync skipped (disabled or missing API key)")
        return
    try:
        with SessionLocal() as db:
            result = sync_dawarich_yesterday(db)
        logger.info("Dawarich scheduled sync finished: %s", result)
    except Exception:
        logger.exception("Dawarich scheduled sync failed")


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    settings = get_settings()
    if not settings.dawarich_sync_enabled:
        logger.info("APScheduler not started (DAWARICH_SYNC_ENABLED=false)")
        return

    _scheduler = BackgroundScheduler(timezone=settings.user_timezone)
    _scheduler.add_job(
        _run_dawarich_sync,
        CronTrigger(hour=settings.dawarich_sync_hour, minute=0),
        id="dawarich_daily_sync",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "APScheduler started: Dawarich sync daily at %02d:00 %s",
        settings.dawarich_sync_hour,
        settings.user_timezone,
    )


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
