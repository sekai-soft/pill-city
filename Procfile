api: FLASK_ENVIRONMENT=development uv run python app.py
worker: uv run celery -A pillcity.tasks worker --loglevel=INFO
beat: uv run celery -A pillcity.tasks beat --loglevel=DEBUG --max-interval 30
web: cd web && npm run start
