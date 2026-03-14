from celery import Celery

from .config import settings

celery_app = Celery(
    "ai_generation_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.task_track_started = True
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
