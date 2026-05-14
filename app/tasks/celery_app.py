# Celery application instance and Beat schedule configuration.

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


celery_app = Celery(
    "expense_sharing",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    # Tell Celery where to find task modules
    include=["app.tasks.email_tasks"]
)

celery_app.conf.beat_schedule = {
    # Runs every Monday at 08:00 UTC
    # crontab(hour, minute, day_of_week): 0=Sunday, 1=Monday, ..., 6=Saturday
    "weekly-balance-summary": {
        "task": "app.tasks.email_tasks.send_weekly_summary",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),
    }
}