from celery import Celery

from app.config import settings

celery_app = Celery(
    "cornerman",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_app.autodiscover_tasks(["app.tasks"])

# Ensure task modules are imported so tasks get registered
import app.tasks.analysis_tasks  # noqa: F401, E402
import app.tasks.video_tasks  # noqa: F401, E402
