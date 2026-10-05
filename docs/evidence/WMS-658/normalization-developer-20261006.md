# WMS-658: проверка разработчика SQL-нормализации, 06.10.2026

Исправление выполнено поверх независимого контракта тестировщика
`d333e31e602d712dadd9989387fbf5fc2c93c0cc`. Это отчёт разработчика,
не перекрёстное ревью и не приёмка аналитика.

`_normalized_cis_sql` теперь обрезает по краям все 29 символов Python
`str.strip()`, включая GS, NBSP и record separator. Порядок удаления BOM,
обычных пробелов, CR/LF и последующего обрезания GS сохранён. Внутренние
TAB/NBSP/record separator остаются значимыми. Python-сравнение, tenant-фильтры,
первый исходный payload, блокировки и обработка конфликтов вставки не менялись.
В существующую PostgreSQL-стадию CI добавлен отдельный запуск всего нового
файла без фильтра маркеров; прежняя команда этапа сохранена.

Все локальные PostgreSQL-прогоны выполнялись последовательно только на
`postgresql+psycopg_async://deniscivkunov@127.0.0.1:5432/wms_test_658_identity_20261006`.
Перед первым прогоном подтверждены имя БД, пользователь и отсутствие других
сессий этой БД. Использованы только синтетические данные штатной fixture.
Интерпретатор: `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python`,
Python 3.14.3. Команды ниже выполнялись из `backend` с этим интерпретатором.

- `python -m pytest -n 0 tests/test_wms658_normalized_identity_regression.py -q --tb=short`
  с указанным `WMS_TEST_DATABASE_URL`: **33 passed**, без skipped/errors, 22.35 s.
- `python -m pytest -n 0 tests/test_wms658_review_regressions_round3.py tests/test_wms658_review_regressions_round4.py tests/test_wms658_review_regressions.py tests/test_wms658_review_regressions_round2.py tests/test_wms658_marking_import_contract.py tests/test_marking_import_pools.py -q --tb=short`
  с тем же `WMS_TEST_DATABASE_URL`: **40 passed**, без skipped/errors, 29.59 s.
- `python -m pytest -n 2 tests/test_wms658_normalized_identity_regression.py -q --tb=line`
  на штатной SQLite: **24 passed, 9 skipped**, 13.16 s; пропуски требуют PostgreSQL.
- `python -m ruff check .`: **All checks passed**.
- `python -m mypy . --no-incremental --cache-dir=/dev/null`:
  **Success: no issues found in 555 source files**.

Дополнительная разовая read-only проверка на той же PostgreSQL сопоставила
875 синтетических SQL-выражений с Python: все пары краевых whitespace,
края с BOM/GS и внутренние символы. Расхождений нет; перечисленный в коде
набор совпадает с полным `chr(...).isspace()` текущего Python (29 символов).
Это дополнительная проверка, не замена замороженного контракта.

Файлы round4 и round3 побайтно совпадают с версиями из
`18c6dd0b3fb50abfd3374c67c37568507755fe09` и
`42a773dcc02256a7b280fc64044e2fc5810c5b1a`. Tests, guards, журнал corrections
и документ требований не изменены.

Ограничения: `python3 scripts/ci/check_task_documents.py 77f6fc1d31ffe6b01a89d61b8f1af8151a5b2d44`
из корня завершился с кодом 1: нет вердиктов C1–C21/C23, а объединённые
ссылки в C7/C9/C10/C12 не разбираются текущей проверкой. Передано для отдельного
продолжения; разработчик не заполнял собственную приёмку и не менял требования.
Отдельное Astra high ревью и приёмка исходного либо замещающего аналитика
ещё необходимы. Полный удалённый CI не запускался. Production, маркетплейсы,
подписи, секреты, деплой и физическая печать не использовались.
