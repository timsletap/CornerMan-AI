"""Usage limits (PLT-05): daily analyses per user and a rolling hourly LLM spend cap.

Days are UTC days, so the daily limit resets at midnight UTC.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.usage import LlmSpend, UsageTracking
from app.models.user import User, UserTier

SPEND_WINDOW = timedelta(hours=1)


def utc_today(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(UTC).date()


def next_daily_reset(now: datetime | None = None) -> datetime:
    """When today's analysis count resets: the next midnight UTC."""
    return datetime.combine(utc_today(now) + timedelta(days=1), time.min, tzinfo=UTC)


def analyses_today(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> int:
    count = (
        db.query(UsageTracking.upload_count)
        .filter(UsageTracking.user_id == user_id, UsageTracking.date == utc_today(now))
        .scalar()
    )
    return int(count or 0)


def check_upload_quota(db: Session, user: User, now: datetime | None = None) -> bool:
    """True if the user may start another analysis today. Pro users are not limited."""
    if user.tier == UserTier.PRO:
        return True
    return analyses_today(db, user.id, now) < settings.FREE_TIER_DAILY_UPLOADS


def increment_upload_count(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> None:
    """Count one analysis against today's limit. The caller commits."""
    today = utc_today(now)
    usage = (
        db.query(UsageTracking)
        .filter(UsageTracking.user_id == user_id, UsageTracking.date == today)
        .with_for_update()
        .first()
    )
    if usage:
        usage.upload_count += 1
    else:
        db.add(UsageTracking(user_id=user_id, date=today, upload_count=1, api_credits_consumed=0.0))


def hourly_llm_spend(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> float:
    """USD spent on LLM calls by this user in the last hour."""
    since = (now or datetime.now(UTC)) - SPEND_WINDOW
    total = (
        db.query(func.coalesce(func.sum(LlmSpend.cost_usd), 0.0))
        .filter(LlmSpend.user_id == user_id, LlmSpend.created_at > since)
        .scalar()
    )
    return float(total or 0.0)


def check_llm_spend_quota(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> bool:
    """True if the user is under the hourly LLM spend cap (API_CREDIT_HOURLY_LIMIT, USD)."""
    return hourly_llm_spend(db, user_id, now) < settings.API_CREDIT_HOURLY_LIMIT


def record_llm_spend(
    db: Session,
    user_id: uuid.UUID,
    session_id: uuid.UUID | None,
    usage: dict,
) -> None:
    """Log one LLM call's actual cost (from coaching `_usage`). Skips calls that cost nothing."""
    cost = float(usage.get("cost_usd", 0.0))
    if cost <= 0:
        return
    db.add(
        LlmSpend(
            user_id=user_id,
            session_id=session_id,
            model=settings.ANTHROPIC_MODEL,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cost_usd=cost,
        )
    )
