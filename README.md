# WMS

Monorepo:

- `backend/`: FastAPI + SQLAlchemy + Alembic
- `frontend/`: React (Vite) + Playwright e2e

## Local dev

```bash
docker compose up -d --build
```

## CI gates (Definition of Done)

- `ruff check .`
- `mypy .`
- `pytest`
- Playwright e2e (user scenarios)

