# Railway staging

Минимальная схема для Railway без локального Docker:

## Services

1. `api`
   - Root directory: `backend`
   - Dockerfile: `backend/Dockerfile.railway`
   - Exposes FastAPI on `$PORT`
   - Runs `alembic upgrade head` before стартом приложения

2. `web`
   - Root directory: `frontend`
   - Dockerfile: `frontend/Dockerfile.railway`
   - Caddy listens on `$PORT`
   - `/api/*` проксируется на backend service или на внешний API URL через `WMS_API_UPSTREAM`

3. `postgres`
   - Railway PostgreSQL plugin
   - `DATABASE_URL` приходит в `api`
   - Backend принимает `postgresql://...` и сам нормализует в `postgresql+psycopg_async://...`

4. `redis` optional
   - Подключать только если на staging нужны Celery workers/beat
   - Пробрасывать в `api` как `CELERY_BROKER_URL`

## Environment variables

### api

- `DATABASE_URL` - Railway Postgres connection string
- `JWT_SECRET_KEY` - длинный случайный секрет
- `WMS_SECRETS_FERNET_KEY` - обязательный секрет для production/staging
- `WMS_CORS_ORIGINS` - дополнительные origins, например `https://web-production.up.railway.app`
- `WMS_BOOTSTRAP_ADMIN=1` - однократный bootstrap первого администратора
- `WMS_BOOTSTRAP_ADMIN_EMAIL`
- `WMS_BOOTSTRAP_ADMIN_PASSWORD`
- `WMS_BOOTSTRAP_ORG_NAME`
- `WMS_BOOTSTRAP_ORG_SLUG`

### web

- `WMS_API_UPSTREAM` - backend service URL или внешний API URL
  - локальный default в Docker: `http://api:8000`
  - для Railway обычно внутренний service URL backend или публичный API URL
- `PORT` - Railway sets this automatically

### optional redis / workers

- `CELERY_BROKER_URL` - redis URL
- `WMS_AUTO_CREATE_SCHEMA` - only for disposable staging/bootstrap flows, not for long-lived prod

## Recommended rollout

1. Create `postgres` first.
2. Create `api` from `backend/Dockerfile.railway`.
3. Point `DATABASE_URL`, `JWT_SECRET_KEY`, `WMS_SECRETS_FERNET_KEY`, and bootstrap envs at `api`.
4. Create `web` from `frontend/Dockerfile.railway`.
5. Set `WMS_API_UPSTREAM` on `web`.
6. Set `WMS_CORS_ORIGINS` on `api` to include the Railway web origin if the browser will talk to the API cross-origin.
7. Flip `WMS_BOOTSTRAP_ADMIN` back to `0` after the first successful boot.

### Build failed сразу после GitHub connect

**Причина:** сервис создан из корня репозитория `/`. В корне WMS нет Dockerfile — Railway не знает, что собирать.

**Исправление:** сервис **WMS** → **Settings** → **Source** → **Root Directory** = `backend` → Save → **Redeploy**.

Фронт — **отдельный** сервис с Root Directory = `frontend`. Postgres — плагин **+ New → Database**.

В репозитории есть `backend/railway.toml` и `frontend/railway.toml` — после смены Root Directory Railway подхватит `Dockerfile.railway` автоматически.

## Smoke after deploy

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
railway link   # один раз, если проект ещё не привязан
# публичный URL web-сервиса из Railway dashboard:
WMS_STAGING_URL=https://your-web.up.railway.app ./scripts/railway-staging-smoke.sh
```

Скрипт проверяет: `GET /` (SPA), `GET /api/health` (через Caddy proxy), наличие root-контейнера React.

Если API на отдельном домене:

```bash
WMS_STAGING_URL=https://web.example.com WMS_STAGING_API_URL=https://api.example.com ./scripts/railway-staging-smoke.sh
```
