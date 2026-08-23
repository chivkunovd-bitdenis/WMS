# 04 warehouse switch — browser scope regression

Проверено на локальном стенде, собранном из commit
`404753461fbd72a832bfac8fd84103defe73639d`.

## Стенд

- FF UI: `http://localhost:15173/`
- API: `http://localhost:18080/health` → `{"status":"ok"}`
- `docker compose ps`: API, FF UI, PostgreSQL и Redis подняты; миграции завершились успешно.

## Тестовые данные

В локальной БД одного tenant созданы две строки:

- `Основной склад` / `physical-main` / `is_operational=true`;
- `FBS WB 777` / `fbs-wb-777` / `is_operational=false`.

Публичный `GET /warehouses` вернул только `Основной склад`. Технический
`FBS WB 777` в ответ не попал.

## Браузерная регрессия

Автоматизированный проход настоящим Chromium подтвердил:

1. На `/app/ff/warehouses` виден `Основной склад`, а `FBS WB 777` отсутствует.
2. `/app/ff/fbs` открывается без ошибок.
3. Между parent `1d3d1d1762cbcd0aa1a55493e04e76028f85475b` и проверяемым commit
   нет ни одного изменённого файла в `frontend/`, поэтому карточка не добавляет
   переключателей, колонок или другого поведения в S-03.

Скриншоты:

- `warehouses-technical-hidden.png`
- `fbs-screen-scope-regression.png`

## Независимое ревью

Независимый Sol-review: `PASS`, блокирующих findings нет. Reviewer отдельно
запустил 14 targeted тестов; все прошли. Отмечены два неблокирующих test gaps:
нет отдельного сценария с реальной строкой `FbsOrderReservation` и нет
двухтранзакционного PostgreSQL race-теста. Защита от дубля в текущей реализации
проверена статически: unique constraint + savepoint; последовательная
идемпотентность покрыта тестом.
