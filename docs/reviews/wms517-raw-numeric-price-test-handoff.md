# WMS-517 F2/R22 — передача тестового контракта

Продуктовая база: `18529be9c`; F2 из `wms517-astra-096475c.md`.
Новый файл: `backend/tests/test_wms517_raw_numeric_price.py`.
Существующие partial Decimal/contract fixtures использованы без изменений.

Тест вызывает публичный POST создания операции. Только HTTP-ответ WB заменён
на сырые JSON bytes: `finishedPrice:1e9999999999999999999` без кавычек;
srid, saleID, date и lastChangeDate берутся из существующего sale fixture.
Проверяются одиночная строка и смешанная страница со здоровым КИЗ, каждый
в режиме исключения и обычного HTTP-ответа. Ожидание: HTTP 200, сохранённый
failed item с invalid_sale_price, исходная лексема в evidence, отсутствие
документа у плохого item; здоровый item остаётся pending с 1234 копейками.
Проверка построения документа здоровой строки уже есть в неизменённом
`test_wms517_sales_partial_decimal_regressions.py`.

Команда из backend:

```sh
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR PYTHONDONTWRITEBYTECODE=1 /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q tests/test_wms517_raw_numeric_price.py --tb=short -p no:cacheprovider
```

RED до исправления: **4 failed**. Два exception-trace варианта доходят до
`wb_sales_report.py:344`, `json.loads(..., parse_float=Decimal, ...)` и падают
с `decimal.InvalidOperation`; два http-status варианта возвращают HTTP 500
вместо ожидаемого 200. Ruff нового файла проходит. База — отдельная SQLite
по PID через conftest; общая PostgreSQL 56517 не использовалась.

Продуктовый код, существующие тесты, секреты, production и Telegram не изменены.
Разработчику: сохранить ожидания и добиться GREEN; ошибка всей страницы
вместо ошибки конкретного item этот контракт не выполняет.
