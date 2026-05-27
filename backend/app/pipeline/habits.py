from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.week import week_dates_sunday_first
from app.models import ActivitySegment, HabitDailyScore, HabitGoal


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _weekday_in_tz(d: date, tz: ZoneInfo) -> int:
    """Monday=0 .. Sunday=6 in user timezone."""
    dt = datetime.combine(d, datetime.min.time(), tzinfo=tz)
    return dt.weekday()


def _duration_for_day(
    db: Session, day: date, activity: str, tz: ZoneInfo
) -> float:
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    segments = (
        db.query(ActivitySegment)
        .filter(
            ActivitySegment.activity_type_slug == activity,
            ActivitySegment.started_at < day_end,
            ActivitySegment.ended_at.isnot(None),
            ActivitySegment.ended_at > day_start,
        )
        .all()
    )
    total = 0.0
    for seg in segments:
        seg_start = _ensure_utc(seg.started_at)
        seg_end = _ensure_utc(seg.ended_at)
        overlap_start = max(seg_start, day_start)
        overlap_end = min(seg_end, day_end)
        if overlap_end > overlap_start:
            total += (overlap_end - overlap_start).total_seconds()
    return total


def _score_daily_min(seconds: float, min_seconds: float) -> float:
    if min_seconds <= 0:
        return 1.0
    return min(1.0, seconds / min_seconds)


def _score_daily_cap(seconds: float, max_seconds: float) -> float:
    if seconds <= max_seconds:
        return 1.0
    if max_seconds <= 0:
        return 0.0
    # Linear decay: 2x cap -> 0
    over = seconds - max_seconds
    return max(0.0, 1.0 - over / max_seconds)


def _score_weekly_total(seconds: float, target_seconds: float) -> float:
    if target_seconds <= 0:
        return 1.0
    return min(1.0, seconds / target_seconds)


def _evaluate_rule(db: Session, rule: dict[str, Any], day: date, tz: ZoneInfo) -> tuple[float, dict[str, Any]]:
    activity = rule.get("activity", "work")
    rule_type = rule["type"]
    weekday = _weekday_in_tz(day, tz)
    days = rule.get("days")

    if days is not None and weekday not in days:
        return 1.0, {"skipped": True, "reason": "day_not_in_rule"}

    seconds = _duration_for_day(db, day, activity, tz)
    details: dict[str, Any] = {"seconds": seconds, "activity": activity}

    if rule_type == "daily_duration":
        min_seconds = rule["min_seconds"]
        score = _score_daily_min(seconds, min_seconds)
        details["min_seconds"] = min_seconds
        return score, details

    if rule_type == "daily_duration_cap":
        max_seconds = rule["max_seconds"]
        score = _score_daily_cap(seconds, max_seconds)
        details["max_seconds"] = max_seconds
        return score, details

    if rule_type == "weekly_duration":
        # Only score on last day of week or aggregate separately
        return 0.0, {"deferred": True}

    raise ValueError(f"Unknown rule type: {rule_type}")


def compute_habits_for_week(db: Session, year: int, week: int) -> list[dict[str, Any]]:
    tz = ZoneInfo(get_settings().user_timezone)
    week_dates = week_dates_sunday_first(year, week)
    goals = db.query(HabitGoal).filter(HabitGoal.is_active.is_(True)).all()

    # Clear existing scores for this week
    db.execute(
        delete(HabitDailyScore).where(
            HabitDailyScore.date.in_(week_dates),
            HabitDailyScore.habit_goal_id.in_([g.id for g in goals]),
        )
    )

    results: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for goal in goals:
        rule = goal.rule_json
        daily_scores: list[dict[str, Any]] = []

        if rule["type"] == "weekly_duration":
            activity = rule.get("activity", "work")
            week_start = datetime.combine(week_dates[0], datetime.min.time(), tzinfo=tz)
            week_end = week_start + timedelta(days=7)
            segments = (
                db.query(ActivitySegment)
                .filter(
                    ActivitySegment.activity_type_slug == activity,
                    ActivitySegment.started_at < week_end,
                    ActivitySegment.ended_at.isnot(None),
                    ActivitySegment.ended_at > week_start,
                )
                .all()
            )
            total = 0.0
            for seg in segments:
                seg_start = _ensure_utc(seg.started_at)
                seg_end = _ensure_utc(seg.ended_at)
                overlap_start = max(seg_start, week_start)
                overlap_end = min(seg_end, week_end)
                if overlap_end > overlap_start:
                    total += (overlap_end - overlap_start).total_seconds()
            score = _score_weekly_total(total, rule["target_seconds"])
            for d in week_dates:
                db.add(
                    HabitDailyScore(
                        habit_goal_id=goal.id,
                        date=d,
                        score=score if d == week_dates[-1] else 0.0,
                        details={"weekly_seconds": total, "target_seconds": rule["target_seconds"]},
                        computed_at=now,
                    )
                )
                daily_scores.append({"date": d.isoformat(), "score": score if d == week_dates[-1] else None})
            week_score = score
        else:
            day_scores_list: list[float] = []
            for d in week_dates:
                score, details = _evaluate_rule(db, rule, d, tz)
                db.add(
                    HabitDailyScore(
                        habit_goal_id=goal.id,
                        date=d,
                        score=score,
                        details=details,
                        computed_at=now,
                    )
                )
                daily_scores.append({"date": d.isoformat(), "score": score, "details": details})
                if not details.get("skipped"):
                    day_scores_list.append(score)
            week_score = sum(day_scores_list) / len(day_scores_list) if day_scores_list else 0.0

        results.append(
            {
                "slug": goal.slug,
                "name": goal.name,
                "week_score": round(week_score, 3),
                "daily": daily_scores,
            }
        )

    db.commit()
    return results
