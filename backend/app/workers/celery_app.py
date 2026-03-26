from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "bballvideo",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=7200,  # 2 hours max per video
    worker_prefetch_multiplier=1,  # One video at a time per worker
)

celery_app.autodiscover_tasks(["app.workers"])
