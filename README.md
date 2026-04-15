# WMS

Monorepo:

- `backend/`: FastAPI + SQLAlchemy + Alembic
- `frontend/`: React (Vite) + Playwright e2e

Решения по MVP и интеграциям: **[docs/MVP_DECISIONS_RU.md](docs/MVP_DECISIONS_RU.md)**.

## Local dev

Поднять всё в Docker:

```bash
docker compose up -d --build
```

Фронт для разработки (Vite) запускать **локально** (из `frontend/`):

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Если API поднят через `docker compose` (дефолтный порт **18080**), Vite сам проксирует `/api/*` на `http://127.0.0.1:18080`.
Если у тебя другой порт API — задай `VITE_API_PROXY`, например:

```bash
VITE_API_PROXY="http://127.0.0.1:28080" npm --prefix frontend run dev
```

Важно: после логина UI по умолчанию открывается в **v2 shell** (маршруты `/app/*`, стартовая — `/app/dashboard`).
Порты **на хосте** (чтобы не пересекаться с другими проектами на том же Mac):

| Сервис | URL / хост-порт | Переменная в `.env` |
|--------|-----------------|---------------------|
| Фронт (Vite) | http://localhost:**15173** | `WMS_WEB_PORT` |
| API | http://localhost:**18080** | `WMS_API_PORT` |
| PostgreSQL | `localhost:5433` | `WMS_DB_PORT` |

Внутри Docker-сети API всё так же ходит в БД как `db:5432`. Если порт занят — положи в корень репозитория `.env`, например:

```env
WMS_DB_PORT=55433
WMS_API_PORT=28080
WMS_WEB_PORT=25173
```

Миграции БД (после изменений схемы):

```bash
cd backend && pip install -e ".[dev]" && alembic upgrade head
```

Первый запуск API в Docker выполняет `alembic upgrade head` перед `uvicorn`.

Интерактивная документация API (Swagger UI): **http://localhost:18080/docs** — это штатно для FastAPI, к регистрации в интерфейсе не привязано.

## Frontend routes (v2)

- Public: `/` (регистрация / логин)
- Authed default: `/app/dashboard`
- Каталог: `/app/catalog`, `/app/catalog/products`
- Операции: `/app/ops`, `/app/ops/inbound`, `/app/ops/outbound`, `/app/ops/movements`, `/app/ops/transfers`
- Интеграции: `/app/integrations/wb`

## CI gates (Definition of Done)

- `ruff check .`
- `mypy .`
- `pytest`
- Playwright e2e (user scenarios)

