import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Get broker and backend from environment variables, or use default local redis
broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

celery_app = Celery(
    'variations_mood',
    broker=broker_url,
    backend=result_backend,
    include=['tasks']
)

# Optional config
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
)

# Configure Celery Beat to run background check
celery_app.conf.beat_schedule = {
    'populate-generated-images-every-minute': {
        'task': 'tasks.run_populate_images',
        'schedule': 60.0,
    },
}

if __name__ == '__main__':
    celery_app.start()
