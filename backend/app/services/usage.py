"""Usage tracking and quota enforcement (LIM-01, LIM-02, LIM-03)."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.config import settings
from app.models.usage import UsageTracking
from app.models.user import User, UserTier


def check_upload_quota(db: Session, user: User) -> bool:
    """LIM-02: Check if user has remaining uploads today."""
    if user.tier == UserTier.PRO:
        return True

    today = date.today()
    usage = db.query(UsageTracking).filter(
        UsageTracking.user_id == user.id,
        UsageTracking.date == today,
    ).first()

    if not usage:
        return True

    return usage.upload_count < settings.FREE_TIER_DAILY_UPLOADS


def check_api_credit_quota(db: Session, user: User) -> bool:
    """LIM-03: Circuit breaker - check if user has exceeded API credit limit."""
    today = date.today()
    usage = db.query(UsageTracking).filter(
        UsageTracking.user_id == user.id,
        UsageTracking.date == today,
    ).first()

    if not usage:
        return True

    return usage.api_credits_consumed < settings.API_CREDIT_HOURLY_LIMIT


def increment_upload_count(db: Session, user_id: uuid.UUID) -> None:
    """Increment today's upload count for a user."""
    today = date.today()
    usage = db.query(UsageTracking).filter(
        UsageTracking.user_id == user_id,
        UsageTracking.date == today,
    ).first()

    if usage:
        usage.upload_count += 1
    else:
        usage = UsageTracking(
            user_id=user_id,
            date=today,
            upload_count=1,
            api_credits_consumed=0.0,
        )
        db.add(usage)
