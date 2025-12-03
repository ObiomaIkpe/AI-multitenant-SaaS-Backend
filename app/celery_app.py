from celery import Celery
from app.config import settings

celery_app = Celery(
    "document_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.autodiscover_tasks(['app'])

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30*60,  # 30 min hard limit
    
    # ADD THESE:
    task_soft_time_limit=25*60,  # 25 min soft limit (graceful shutdown)
    
    # Task routing by type (better resource management)
    task_routes={
        'app.tasks.embedding.*': {'queue': 'embeddings'},
        'app.tasks.ingestion.*': {'queue': 'ingestion'},
        'app.tasks.vectorization.*': {'queue': 'vectorization'},
    },
    
    # Worker settings for long-running tasks
    worker_prefetch_multiplier=1,  # Important for long tasks
    worker_max_tasks_per_child=1000,  # Prevent memory leaks
    
    # Result management
    result_expires=3600,  # Clean up results after 1 hour
    
    # Reliability
    task_acks_late=True,  # Re-queue on worker crash
    task_reject_on_worker_lost=True,
    
    # Rate limiting baseline
    task_default_rate_limit='100/m',  # Adjust per needs
)