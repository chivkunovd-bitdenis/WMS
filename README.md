# WMS

Monorepo:

- `backend/`: FastAPI + SQLAlchemy + Alembic
- `frontend/`: React (Vite) + Playwright e2e

Решения по MVP и интеграциям: **[docs/MVP_DECISIONS_RU.md](docs/MVP_DECISIONS_RU.md)**.

## Local dev

```bash
docker compose up -d --build
```

Миграции БД (после изменений схемы):

```bash
cd backend && pip install -e ".[dev]" && alembic upgrade head
```

Первый запуск API в Docker выполняет `alembic upgrade head` перед `uvicorn`.

## CI gates (Definition of Done)

- `ruff check .`
- `mypy .`
- `pytest`
- Playwright e2e (user scenarios)

