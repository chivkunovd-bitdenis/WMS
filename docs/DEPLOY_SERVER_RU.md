# Деплой на сервер (prod)

Канонический путь: **PR → merge в `main` → зелёный CI на `main` → git pull + docker compose** на сервере. Секреты только в `.env` на сервере.

**Запрещено:** `git push origin main` с рабочей машины или агента; деплой с ветки, которая не влita через PR. Подробно: **`AGENTS.md` → Release to prod (PR-only)**.

## Релиз (каждая фича / фикс)

1. Ветка от `main`: `git checkout -b feat/…`
2. Код + тесты; локально: `backend/` → `ruff check . && mypy . && pytest`; `frontend/` → `npm run build && npm run test:e2e`
3. Push ветки: `git push -u origin HEAD`
4. PR: `gh pr create` (блок `### Test coverage` — см. `AGENTS.md`, если CI требует)
5. Дождаться **зелёного CI на PR** → **Merge**
6. Дождаться **зелёного CI на `main`** (workflow после merge)
7. На сервере: `./scripts/deploy/prod-update.sh`

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

## CI (GitHub Actions)

На каждый **PR** и push в `main` (после merge):

- `backend`: ruff, mypy, pytest
- `frontend`: build, Playwright e2e
- проверки Test coverage в PR

**Merge в `main` только при зелёном CI на PR.** После merge — CI на `main` должен быть зелёным **до** `git pull` на прод.

### Branch protection (рекомендуется включить)

- Require pull request before merging
- Require status checks (backend, e2e, …)
- **Do not allow bypassing** for admins — иначе агенты с `gh`/git снова смогут пушить в `main` в обход PR

## Проверка после деплоя

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -n 50 api
curl -fsS "https://${WMS_PUBLIC_DOMAIN}/api/health" || true
```
