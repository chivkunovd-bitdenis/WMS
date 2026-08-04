# Compose survey — fbs-wb-emulator (test wiring only)

Обзор перед добавлением `wb-emulator`. **Код и compose не менялись** — только документ.

## Какие compose-файлы есть

| Файл | Назначение |
|------|------------|
| `docker-compose.yml` | Локальная dev/test стек: `db`, `redis`, `api`, `celery_worker`, `celery_beat`, `web`, `web_seller` |
| `docker-compose.prod.yml` | Прод: `db`, `redis`, `api`, `celery_worker`, `celery_beat`, `web` (без `web_seller`) |
| `docker-compose.wms-host-8088.yml` | Overlay для сервера: порт web `8088`, свой Caddyfile |

Паттерн overlay уже используется: `docker compose -f docker-compose.prod.yml -f docker-compose.wms-host-8088.yml`.

Ни в одном файле **нет** `env_file:` — переменные задаются inline в `environment:` или через `${VAR}` из shell/.env при запуске compose.

## Где `api` / `celery_worker` / `celery_beat` получают env

### `docker-compose.yml` (локальный)

| Сервис | `environment:` (явно в файле) |
|--------|-------------------------------|
| **api** | `DATABASE_URL`, `CELERY_BROKER_URL`, `WMS_DATA_DIR`, bootstrap-админ (`WMS_BOOTSTRAP_*`) |
| **celery_worker** | `DATABASE_URL`, `CELERY_BROKER_URL` |
| **celery_beat** | `DATABASE_URL`, `CELERY_BROKER_URL` |

`WILDBERRIES_MARKETPLACE_API_BASE` **не задан** → Pydantic берёт дефолт `https://marketplace-api.wildberries.ru` из `settings.wildberries_marketplace_api_base`.

### `docker-compose.prod.yml` (прод)

| Сервис | Ключевые env |
|--------|----------------|
| **api** | `DATABASE_URL`, `CELERY_BROKER_URL`, `JWT_SECRET_KEY`, `WMS_SECRETS_FERNET_KEY`, S3, `WMS_CORS_ORIGINS` |
| **celery_worker** | `DATABASE_URL`, `CELERY_BROKER_URL`, `JWT_SECRET_KEY`, `WMS_SECRETS_FERNET_KEY` |
| **celery_beat** | `DATABASE_URL`, `CELERY_BROKER_URL`, `JWT_SECRET_KEY`, `WMS_SECRETS_FERNET_KEY` |

WB Marketplace base **не задан** → реальный WB на проде.

### `docker-compose.wms-host-8088.yml`

Только overlay для `web` (порты, Caddyfile, `WMS_PUBLIC_DOMAIN`). **api/celery не трогает.**

## Рекомендация: test-only wiring

**Вариант A — отдельный override-файл `docker-compose.emulator.yml` (рекомендуется)**

- Добавить сервис `wb-emulator` (build `wb_emulator/`, volume SQLite, mount seed).
- В том же файле — **patch** `api`, `celery_worker`, `celery_beat`: `WILDBERRIES_MARKETPLACE_API_BASE=http://wb-emulator:8000`, `depends_on: wb-emulator`.
- Запуск: `docker compose -f docker-compose.yml -f docker-compose.emulator.yml up -d --build`
- Прод: `docker compose -f docker-compose.prod.yml up` **без** второго файла → эмулятор не поднимается, env не подставляется.

Плюсы: совпадает с `docker-compose.wms-host-8088.yml`; явный opt-in; нулевой риск для prod; не засоряет базовый `docker-compose.yml` для тех, кто не тестирует FBS.

**Вариант B — compose profile `emulator`**

- Сервис `wb-emulator` с `profiles: [emulator]`; env на WMS через `profiles` или условные extends.
- Запуск: `docker compose --profile emulator up`
- Минусы: profile на env-блоках WMS менее прозражен; легко забыть профиль и думать, что FBS идёт в эмулятор.

**Вариант C (Agent default)** — то же, что **A**: override-файл, не prod, не правки `backend/app`.

## Proof: prod чист от эмулятора (текущее состояние)

Поиск по репо (`docker-compose*.yml`):

- `emulator` — **0 совпадений**
- `WILDBERRIES_MARKETPLACE` — **0 совпадений**
- `wb-emulator` — **0 совпадений**

`docker-compose.prod.yml` не определяет сервис эмулятора и не задаёт `WILDBERRIES_MARKETPLACE_API_BASE`. Marketplace-вызовы на проде идут на дефолт `https://marketplace-api.wildberries.ru`.

## Черновик команды после реализации (не применять сейчас)

```bash
docker compose -f docker-compose.yml -f docker-compose.emulator.yml up -d --build
```

Проверка, что WMS бьёт в эмулятор: логи `wb-emulator` при автопросе / `POST /__admin/orders` + отсутствие исходящих запросов на `marketplace-api.wildberries.ru` из worker.
