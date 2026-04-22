# WMS

Monorepo:

- `backend/`: FastAPI + SQLAlchemy + Alembic
- `frontend/`: React (Vite) + Playwright e2e

Решения по MVP и интеграциям: **[docs/MVP_DECISIONS_RU.md](docs/MVP_DECISIONS_RU.md)**.

Целевой бизнес‑процесс (source of truth): **[docs/BUSINESS_PROCESS_SELLER_INBOUND_OUTBOUND_RU.md](docs/BUSINESS_PROCESS_SELLER_INBOUND_OUTBOUND_RU.md)**.

## Local dev

Поднять всё в Docker:

```bash
docker compose up -d --build
```

## Dev access (как быстро восстановить логин)

Пароли **не храним в git** (в БД они лежат как bcrypt‑хеш, «вытащить» исходный пароль нельзя).
Если разлогинился и не можешь войти — делай **reset** на новый пароль, который знаешь.

### Если Docker работает (Postgres в compose)

1) Узнать email пользователей фулфилмента:

```bash
docker compose exec -T db psql -U postgres -d wms -c "select email, role from users order by created_at desc;"
```

2) Сбросить пароль для нужного email (пример: `fulfillment_admin@example.com`):

```bash
docker compose exec -T api python - <<'PY'
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.settings import settings
from app.services.passwords import hash_password

EMAIL = "fulfillment_admin@example.com"
NEW_PASSWORD = "CHANGE_ME_NOW_123!"

async def main() -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(
            text("update users set password_hash=:h, must_set_password=false where email=:e"),
            {"h": hash_password(NEW_PASSWORD), "e": EMAIL},
        )
        await s.commit()
    await engine.dispose()
    print("OK")

asyncio.run(main())
PY
```

### Если Docker не работает (локальный API на SQLite)

Можно поднять API локально с SQLite (порт 18080), затем создать/сбросить доступ.

Запуск API:

```bash
cd backend
export DATABASE_URL="sqlite+aiosqlite:////absolute/path/to/backend/dev.db"
export WMS_AUTO_CREATE_SCHEMA=1
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 18080
```

Reset пароля в SQLite:

```bash
cd backend
export DATABASE_URL="sqlite+aiosqlite:////absolute/path/to/backend/dev.db"
python3 - <<'PY'
import asyncio
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.user import User
from app.services.passwords import hash_password

EMAIL = "fulfillment_admin@example.com"
NEW_PASSWORD = "CHANGE_ME_NOW_123!"

async def main() -> None:
    async with SessionLocal() as s:
        res = await s.execute(select(User).where(User.email == EMAIL))
        u = res.scalar_one_or_none()
        if u is None:
            raise SystemExit("NOT_FOUND")
        u.password_hash = hash_password(NEW_PASSWORD)
        u.must_set_password = False
        await s.commit()
    print("OK")

asyncio.run(main())
PY
```

**Важно про «старый» UI в `docker compose`:** сервис `web` собирается из `frontend/Dockerfile` командой `COPY .` и внутри контейнера крутит **`npm run dev` (Vite)**. Исходники **не монтируются** с хоста: после `git pull` или смены ветки фронт в контейнере обновится **только** после пересборки образа, например:

```bash
docker compose build --no-cache web && docker compose up -d web
```

или одной командой `docker compose up -d --build`. Если всё ещё видите старый бандл — сначала `docker compose build --no-cache web`.

**Прод** (`docker-compose.prod.yml`): фронт — это **статический билд** (`npm run build` в `frontend/Dockerfile.prod` + Caddy). После изменений фронта достаточно `docker compose -f docker-compose.prod.yml up -d --build web` (или полного стека). Корневой `.dockerignore` исключает `frontend/node_modules` и `frontend/dist`, чтобы в образ не попали артефакты с машины разработчика.

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

## Production (Docker Compose)

В проде фронт **собирается внутри Docker** и отдаётся как статика через Caddy (Node на сервере не нужен).
API доступен только через тот же домен/порт по пути `/api/*`.

### Первичный запуск

1) На сервере в корне репозитория создать `.env` (в git не коммитить), минимум:

```env
# внешний порт (Caddy) — 80 внутри контейнера
WMS_HTTP_PORT=8080

# БД
POSTGRES_DB=wms
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change-me

# API security (обязательно в проде)
JWT_SECRET_KEY=change-me-use-long-random-secret
WMS_SECRETS_FERNET_KEY=change-me-urlsafe-base64-fernet-key
```

2) Поднять стек:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Обновление (канонично)

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

### Доступ

- UI (Fulfillment): `http://<server>:${WMS_HTTP_PORT:-8080}/`
- UI (Seller portal, отдельное SPA): `http://<server>:${WMS_HTTP_PORT:-8080}/seller/`
- API: `http://<server>:${WMS_HTTP_PORT:-8080}/api/...`

Примечание по reverse proxy: в проде Caddy проксирует **`/api/*` → FastAPI**, при этом префикс **`/api` снимается** (внутри API маршруты как в Swagger: `/health`, `/auth/login`, …).

## Frontend routes (v2)

### Fulfillment portal (бандл `index.html`, публичный путь `/`)

- Public: `/` (регистрация фулфилмента / логин)
- Authed shell (MUI): `/app/*`; стартовая точка **`/app/dashboard` → `/app/ff/dashboard`**
- Дашборд ФФ: `/app/ff/dashboard` (недельный календарь, сводки inbound/outbound)
- Поставки и загрузки / Supply and Load (единый список): `/app/ff/supplies-shipments`
- Заглушки: `/app/ff/products`, `/app/ff/honest-sign`
- Каталог (склады и ячейки): `/app/catalog`, `/app/catalog/products` (в сайдбаре ФФ также ведёт сюда пункт «Склады и ячейки»)
- Операции: `/app/ops`, `/app/ops/inbound`, `/app/ops/outbound`, `/app/ops/movements`, `/app/ops/transfers`
- Интеграции WB: `/app/integrations/wb` (редирект с `/app/ff/integrations/wb`)

### Seller portal (отдельный бандл `seller/index.html`, публичный путь `/seller/`)

- Public/auth: `/seller/` (логин/регистрация — как в текущем seller UI)
- Документы: `/seller/documents`
- Товары: `/seller/products`
- Настройки: `/seller/settings`
- Черновик inbound: `/seller/inbound/new` и `/seller/inbound/:id`

Локально в Vite (multi-page) удобная точка входа seller-приложения: `http://localhost:15173/seller/index.html` (если поднят `npm --prefix frontend run dev`).

## CI gates (Definition of Done)

- `ruff check .`
- `mypy .`
- `pytest`
- Playwright e2e (user scenarios)

