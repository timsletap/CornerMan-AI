"""Celery tasks for the analysis pipeline (Vision + Coaching)."""

import json
import logging
import uuid
from datetime import UTC, date, datetime

from app.database import SessionLocal
from app.models.analysis import AnalysisSession, AnalysisStatus
from app.models.drill import Drill, DrillRecommendation
from app.models.error_flag import ErrorFlag, ErrorType, Severity
from app.models.strike import Hand, StrikeEvent, StrikeType
from app.models.usage import UsageTracking
from app.models.user import User
from app.models.video import Video
from app.services.coaching import generate_coaching_feedback
from app.services.progress import clear_progress, update_progress
from app.services.video import get_video_path
from app.services.vision import run_vision_analysis
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

STRIKE_TYPE_MAP = {
    "jab": StrikeType.JAB,
    "cross": StrikeType.CROSS,
    "hook": StrikeType.HOOK,
    "uppercut": StrikeType.UPPERCUT,
    "body_shot": StrikeType.BODY_SHOT,
    "elbow": StrikeType.ELBOW,
    "knee": StrikeType.KNEE,
    "kick": StrikeType.KICK,
}

HAND_MAP = {
    "left": Hand.LEFT,
    "right": Hand.RIGHT,
}

ERROR_TYPE_MAP = {
    "dropped_guard": ErrorType.DROPPED_GUARD,
    "chicken_wing": ErrorType.CHICKEN_WING,
}

SEVERITY_MAP = {
    "low": Severity.LOW,
    "medium": Severity.MEDIUM,
    "high": Severity.HIGH,
}


@celery_app.task(
    name="tasks.run_analysis_pipeline",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run_analysis_pipeline(self, session_id: str, video_id: str) -> dict:
    """Orchestrate the full analysis pipeline for a video.

    Steps:
    1. Update session status to PROCESSING
    2. Run vision pipeline (VIS-01 through VIS-07)
    3. Persist strike events and error flags
    4. Run coaching agent (AGT-01 through AGT-04)
    5. Persist coach feedback and drill recommendations
    6. Update session status to COMPLETED
    """
    db = SessionLocal()
    try:
        sid = uuid.UUID(session_id)
        vid = uuid.UUID(video_id)

        session = db.query(AnalysisSession).filter(AnalysisSession.id == sid).first()
        video = db.query(Video).filter(Video.id == vid).first()
        user = db.query(User).filter(User.id == session.user_id).first()

        if not session or not video or not user:
            logger.error("Session, video, or user not found: %s / %s", session_id, video_id)
            return {"status": "failed", "error": "Records not found"}

        # 1. Set status to PROCESSING
        session.status = AnalysisStatus.PROCESSING
        session.processing_started_at = datetime.now(UTC)
        db.commit()

        update_progress(session_id, "initializing", 0.0, "Loading video and YOLO model...")

        # 2. Resolve video path and run vision pipeline
        video_path = get_video_path(video)
        logger.info("Running vision analysis on %s for session %s", video_path, session_id)
        vision_json = run_vision_analysis(video_path, sid)

        # 3. Persist vision results on session
        update_progress(session_id, "persisting", 0.90, "Saving analysis results...")

        metrics = vision_json.get("metrics", {})
        session.vision_json = vision_json
        session.total_strikes = metrics.get("total_strikes", 0)
        session.avg_velocity = metrics.get("avg_velocity", 0.0)
        session.guard_score = metrics.get("guard_score", 100.0)

        # Store annotated video path
        annotated_path = vision_json.get("annotated_video_path")
        if annotated_path:
            session.annotated_video_path = annotated_path

        # 4. Persist StrikeEvent rows
        strike_events_data = vision_json.get("strike_events", [])
        strike_db_objects = []
        for se in strike_events_data:
            strike_type = STRIKE_TYPE_MAP.get(se.get("strike_type", ""), StrikeType.OTHER)
            hand = HAND_MAP.get(se.get("hand", ""), Hand.RIGHT)

            strike_obj = StrikeEvent(
                session_id=sid,
                timestamp_ms=se.get("timestamp_ms", 0),
                frame_number=se.get("frame_number", 0),
                strike_type=strike_type,
                hand=hand,
                velocity=se.get("velocity"),
                keypoints=se.get("keypoints"),
            )
            db.add(strike_obj)
            strike_db_objects.append(strike_obj)

        db.flush()

        # 5. Persist ErrorFlag rows linked to strikes
        error_flags_data = vision_json.get("error_flags", [])
        for ef in error_flags_data:
            error_type = ERROR_TYPE_MAP.get(ef.get("error_type", ""), ErrorType.OTHER)
            severity = SEVERITY_MAP.get(ef.get("severity", ""), Severity.MEDIUM)

            related_idx = ef.get("related_strike_index")
            strike_event_id = None
            if related_idx is not None and 0 <= related_idx < len(strike_db_objects):
                strike_event_id = strike_db_objects[related_idx].id

            error_obj = ErrorFlag(
                session_id=sid,
                strike_event_id=strike_event_id,
                error_type=error_type,
                timestamp_ms=ef.get("timestamp_ms", 0),
                frame_number=ef.get("frame_number", 0),
                severity=severity,
                details=ef.get("details"),
            )
            db.add(error_obj)

        db.flush()

        # 6. Run coaching agent
        update_progress(session_id, "coaching", 0.92, "Generating AI coaching feedback...")

        user_profile = {
            "stance": user.stance.value if user.stance else "unknown",
            "experience_level": user.experience_level.value if user.experience_level else "unknown",
            "weight_class": user.weight_class.value if user.weight_class else "unknown",
        }

        logger.info("Generating coaching feedback for session %s", session_id)
        coaching_response = generate_coaching_feedback(vision_json, user_profile)

        # 7. Persist coach feedback
        session.coach_feedback = json.dumps(coaching_response)

        # 8. Create DrillRecommendation rows from mapped_drills
        update_progress(session_id, "drills", 0.96, "Mapping drill recommendations...")

        mapped_drills = coaching_response.get("mapped_drills", [])
        for priority, drill_name in enumerate(mapped_drills):
            drill = db.query(Drill).filter(Drill.name == drill_name).first()
            if drill:
                drill_rec = DrillRecommendation(
                    session_id=sid,
                    drill_id=drill.id,
                    priority=priority,
                )
                db.add(drill_rec)

        # 9. Update usage tracking with API credits
        usage_info = coaching_response.get("_usage", {})
        _update_api_credits(db, user.id, float(usage_info.get("cost_usd", 0.0)))

        # 10. Mark session as completed
        update_progress(session_id, "complete", 1.0, "Analysis complete!")

        session.status = AnalysisStatus.COMPLETED
        session.processing_completed_at = datetime.now(UTC)
        db.commit()

        clear_progress(session_id)

        logger.info("Analysis pipeline completed for session %s", session_id)
        return {
            "session_id": session_id,
            "status": "completed",
            "total_strikes": metrics.get("total_strikes", 0),
            "guard_score": metrics.get("guard_score", 100.0),
        }

    except Exception as exc:
        db.rollback()
        logger.exception("Analysis pipeline failed for session %s: %s", session_id, exc)

        try:
            session = (
                db.query(AnalysisSession)
                .filter(AnalysisSession.id == uuid.UUID(session_id))
                .first()
            )
            if session:
                session.status = AnalysisStatus.FAILED
                db.commit()
        except Exception:
            db.rollback()

        update_progress(session_id, "failed", 0.0, f"Analysis failed: {exc}")
        raise self.retry(exc=exc) from exc

    finally:
        db.close()


def _update_api_credits(db, user_id: uuid.UUID, cost: float) -> None:
    """Add API credit cost to today's usage tracking record."""
    today = date.today()
    usage = (
        db.query(UsageTracking)
        .filter(
            UsageTracking.user_id == user_id,
            UsageTracking.date == today,
        )
        .first()
    )

    if usage:
        usage.api_credits_consumed += cost
    else:
        usage = UsageTracking(
            user_id=user_id,
            date=today,
            upload_count=0,
            api_credits_consumed=cost,
        )
        db.add(usage)
