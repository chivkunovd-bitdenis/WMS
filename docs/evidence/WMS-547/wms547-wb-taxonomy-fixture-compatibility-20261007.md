# WMS-547 · C4 WB seller-info и taxonomy-запросы WMS-658

Дата: 07.10.2026. Это доказательство исправления только тестовой фикстуры;
продуктовый код не изменялся.

## Подтверждённый исходный RED

В переданном raw-логе shard 0
`/Users/deniscivkunov/Projects/WMS/.agent-runs/night-20261006-01a112a8/integration/pr393-backend-shard0-c3.log`
зафиксирован сбой C4:

```text
assert seller_info_calls == 1
E assert 2 == 1
```

Стек лога показывает, что второй вызов не был повтором
`GET /api/v1/seller-info`: общая подмена `svc.httpx.AsyncClient` перехватила
новый обязательный для WMS-658 запрос
`GET /content/v2/object/parent/all`. Старая фикстура увеличивала счётчик до
проверки `request.url.path`, поэтому taxonomy GET ошибочно считался вызовом
seller-info. В этом же логе видно, что assert старого handler остановил
taxonomy-загрузку до обращения к `/content/v2/object/all`.

## Сохранённый контракт

`test_c4_wb_self_service_creates_requisites_with_single_call_and_journal_event`
по-прежнему требует ровно один `GET /api/v1/seller-info`. Отдельно он теперь
разрешает только два GET WMS-658 — сначала
`/content/v2/object/parent/all`, затем `/content/v2/object/all` с
`limit=1000&offset=0`. У всех трёх запросов проверяется исходный WB token;
любой другой путь, метод, параметры или токен делает фикстуру красной.
Проверки созданных реквизитов, ручных значений и одного события журнала не
изменены.

## GREEN после корректировки

Выполнен один адресный процесс через существующий `backend/.venv`, без новых
зависимостей и без xdist:

```sh
cd backend
WMS_TEST_DATABASE_URL=sqlite+aiosqlite:///:memory: \
WMS_TEST_DATA_DIR="$(mktemp -d /private/tmp/wms658-requisites-tests.XXXXXX)" \
PYTHONDONTWRITEBYTECODE=1 \
.venv/bin/python -m pytest -n 0 -p no:cacheprovider --tb=short \
  tests/test_seller_requisites_autofill.py
```

Результат: **13 passed, 6 warnings, 17.50s**. Предупреждения существующие,
депрекационные; пропусков нет.
