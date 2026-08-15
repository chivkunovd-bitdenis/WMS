# Деплой на сервер (prod)

Канонический путь: **git fetch + проверка ствола + docker compose** на сервере.
Секреты только в `.env` на сервере.

## Требования

- Docker + Docker Compose v2
- Git
- DNS A/AAAA на `WMS_PUBLIC_DOMAIN` (для HTTPS через Caddy в образе `web`)

## Первый запуск

```bash
git clone https://github.com/chivkunovd-bitdenis/WMS.git /opt/wms
cd /opt/wms
cp deploy/env.prod.example .env
# Отредактировать .env: WMS_PUBLIC_DOMAIN, POSTGRES_PASSWORD, JWT_SECRET_KEY, …
docker compose -f docker-compose.prod.yml up -d --build
```

Миграции БД выполняет `celery_worker` при старте: `alembic upgrade head`.

## Порт 8088 (если 80/443 заняты)

На сервере `194.87.96.144` используется overlay:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.wms-host-8088.yml up -d --build
```

UI: `http://194.87.96.144:8088/` (FF), `http://194.87.96.144:8088/seller/` (селлер).

Скрипт `scripts/deploy/prod-update.sh` подхватывает `docker-compose.wms-host-8088.yml` автоматически, если файл есть.

## Обновление (каждый релиз)

```bash
cd /opt/wms
./scripts/deploy/prod-update.sh
```

По умолчанию скрипт деплоит `origin/etalon` и перед сборкой проверяет, что выбранный
commit уже содержится в разрешённом стволе (`WMS_DEPLOY_TRUNK_REF`, по умолчанию
`origin/etalon`). Деплой произвольной рабочей ветки блокируется. Для аварийного
изменения ветка сначала вливается в ствол, после этого запускается деплой.

## CI / CD (GitHub Actions)

### CI — PR и ручной запуск

Workflow `.github/workflows/ci.yml`:

- `backend`: ruff, mypy, pytest
- `frontend`: build, Playwright e2e (85+ сценариев)
- PR: Test coverage + TC-ID в e2e

### CD — ручной деплой только из ствола

Workflow `.github/workflows/deploy.yml`:

1. Триггер: только вручную (*Actions → Deploy Production → Run workflow*) после явного решения о выкатке.
2. SSH на сервер → `./scripts/deploy/prod-update.sh` (`git fetch` + checkout разрешённой ветки + deploy guard + `docker compose up -d --build` + миграции через celery_worker + WB re-sync).
3. Smoke: HTTP 200 на `/`, `/seller/`, `/api/health`.

**Secrets** (Settings → Secrets and variables → Actions):

| Secret | Пример |
|--------|--------|
| `DEPLOY_SSH_HOST` | `194.87.96.144` |
| `DEPLOY_SSH_USER` | `root` |
| `DEPLOY_SSH_KEY` | private ed25519 key (только deploy, не личный) |
| `DEPLOY_SSH_PORT` | `22` |
| `DEPLOY_HTTP_PORT` | `8088` |

Ключ `github-actions-wms-deploy` — в `authorized_keys` на сервере. Ротация: новый ключ → secret → pubkey на сервере.

## Проверка после деплоя

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -n 50 api
curl -fsS "https://${WMS_PUBLIC_DOMAIN}/api/health" || true
```
