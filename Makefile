.PHONY: help dev docker-up docker-down migrate test lint

help:
	@echo "Команди:"
	@echo "  make dev         — запустити сервер локально"
	@echo "  make docker-up   — запустити через Docker"
	@echo "  make docker-down — зупинити Docker"
	@echo "  make migrate     — виконати міграції БД"
	@echo "  make test        — запустити тести"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

docker-up:
	docker-compose up -d --build

docker-down:
	docker-compose down

migrate:
	alembic upgrade head

migrate-create:
	@read -p "Назва міграції: " name; \
	alembic revision --autogenerate -m "$$name"

test:
	pytest -v --cov=app --cov-report=term-missing

celery-worker:
	celery -A app.workers.celery_app worker --loglevel=info --concurrency=4

celery-beat:
	celery -A app.workers.celery_app beat --loglevel=info
