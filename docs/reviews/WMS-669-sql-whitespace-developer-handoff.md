# WMS-669 · D1 SQL whitespace: передача разработчика

06.10.2026. База — опубликованный контракт
`a9974cebb3fcdd82d2a2541d1fe6cddb044b21f6`.
До правки повторён его RED: **6 failed, 5 passed**, 4.38 s;
все падения — целевые AssertionError, не ошибки подготовки.

Изменён только `backend/app/services/seller_fulfillment_catalog_service.py`:
встроенному SQL `trim` передан полный набор из 29 пробельных символов Python
`str.strip()`. Он используется для категории карточки, строковых techSize/wbSize
и сохранённого размера товара. Проверка строкового типа JSON, fallback wbSize,
выбор собственного варианта через ProductBarcode и корреляция SQL сохранены.
Готового общего SQL helper/набора символов при целевом поиске не найдено.
Новых функций PostgreSQL, таблиц и источников остатка нет.

## Проверки

Замороженные файлы запуска: `test_wms669_sql_whitespace_regression.py`,
`test_wms669_seller_catalog_contract.py`, `test_wms669_seller_catalog_once.py`,
`test_wms669_visible_metadata_regression.py`, `test_wms548_seller_catalog_page.py`,
`test_seller_wb_catalog_isolation.py` (все в `backend/tests`).
Общий набор: новые 6, прежние 41 и отдельная PostgreSQL-проверка C10.

SQLite: **47 passed, 1 skipped**, 23.98 s; пропущен только PostgreSQL C10.
PostgreSQL: **48 passed**, 25.39 s, без пропусков. Проверены категории и размеры,
page/keys, total/страницы, seller/tenant fence и снимок всей БД до/после чтения
(C10): баланс, резерв, лимиты и карточки не изменились.
Каждый SQLite-запуск использовал собственный TemporaryDirectory и новую БД,
`-n 0 -p no:cacheprovider -q --tb=short`, PYTHONDONTWRITEBYTECODE=1.

Дополнительно реальные SQLite/PostgreSQL SQL-выражения проверены на каждом из
29 символов, пустой строке, NULL и двух непробельных контролях U+200B/U+FEFF.
Набор сопоставлен со всеми Unicode code points текущего Python через isspace();
результат trim совпал с strip() на обоих движках.

Ruff изменённого сервиса — PASS. Целевой mypy с `--follow-imports=silent
--cache-dir=/dev/null` — PASS, один файл. `git diff --check` — PASS.
Тесты, фикстуры, guards и требования побайтно сохранены относительно базы.

## Изоляция PostgreSQL и дальнейшие этапы

Использован существующий тестовый кластер PostgreSQL 17.10
`/private/tmp/wms669-contract-pg-20261006`, описанный в исходной передаче WMS-669.
До запуска проверены владелец каталога, postmaster.opts, отсутствие сервера,
слушателя и другого тестового процесса. Порт 56669, loopback, роль wms669_test;
создана только собственная база `wms_test_669_d1_developer_20261006`.
Другие базы и серверы, включая 55466/56517, не использовались.

Первый PostgreSQL-прогон: 42 passed, 6 setup errors из-за asyncpg pool между
разными asyncio loops. Тесты и код подготовки не менялись; повтор использует
`-o asyncio_default_test_loop_scope=session
-o asyncio_default_fixture_loop_scope=session`.
URL этого запуска —
`postgresql+asyncpg://wms669_test@127.0.0.1:56669/wms_test_669_d1_developer_20261006`;
остальные параметры и шесть файлов перечислены выше, WMS_TEST_DATA_DIR —
собственный TemporaryDirectory. После проверки база удалена, кластер остановлен;
перед остановкой других клиентов не было. Новый кластер не создавался.

Это передача реализации D1, не независимое ревью и не приёмка WMS-669.
Ведущий проводит отдельное Astra high delta-ревью точного опубликованного SHA;
аналитик закрывает приёмку и документы до полного CI. Навыки, агенты, браузер,
секреты, live-системы, merge и деплой не использовались.
