import os

import celery
from celery.utils.log import get_task_logger

app = celery.Celery(
    "tasks",
    broker=os.environ["REDIS_URL"],
    include=["pillcity.tasks.generate_link_preview", "pillcity.tasks.process_image"],
)
logger = get_task_logger(__name__)

app.conf.timezone = "UTC"
