.PHONY: up down install migrate seed run test lint

up:
	docker compose up -d

down:
	docker compose down

install:
	pip install -e ".[dev]"

migrate:
	alembic upgrade head

seed:
	python -m scripts.seed_exams

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -q

lint:
	ruff check app tests
	ruff format --check app tests
