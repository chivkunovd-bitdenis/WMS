# WMS-662 · F3 · контракт тестов до исправления

Источник: `astra-review-956cd8a.md`, F3, требования R3/R6/R14.
Новый контракт: `backend/tests/test_wms662_continued_billing.py`.
Существующий `test_wms662_approve_scope_race.py` не изменён: его frozen helpers
и полные assertions первого approve/retry вызываются напрямую.

На HEAD `bee6f687c53d9f9844fce037c4dd845c4dd83df0` product diff
`git diff 956cd8a35 -- backend/app` пуст. Это RED на продуктовой версии 956cd8a35,
а не на новом исправлении. Запуск двух вариантов: **2 failed, 6 warnings in 1.93s**.
Оба падают на целевом бизнес-assert:
`F3: completed two units but charges retain first unit only: ['1.0000', '1.0000']`.

До этого прошли: approve сохранённого A/1 при текущем A/2, расход 1, резерв 1,
факт/начисления 1, same-key retry без внешних запросов; затем настоящий observed
sync `delivering`, SKU/qty=2, расход 2, резерв 0 и завершение поставки.
Вариант repeated-sync дополнительно выполняет два опроса и проверяет неизменность
ID/количеств/сумм движений, фактов, строк факта и начислений до целевого RED.
Контракт также требует итоговый единственный факт с item_quantity=2, строки товара
с суммарным количеством 2 и два начисления разных услуг по 2 единицы.

Команда из backend: `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m
pytest -q -p no:cacheprovider tests/test_wms662_continued_billing.py --tb=short`.
Перед запуском явно заданы собственные случайные `WMS_TEST_DATABASE_URL`
(sqlite+aiosqlite) и `WMS_TEST_DATA_DIR` в новом каталоге временных данных.
PostgreSQL не использован. Frozen no-network fixture блокирует сеть;
OzonCards разрешает только чтение, approve transport не вызывается повторно.
Секреты, production, продуктовый код и исходные assertions не менялись.

Передача разработчику: исправить F3, сохранив этот контракт и исходные frozen
контракты без изменения ожиданий. Этот отчёт фиксирует RED; PASS, независимое
ревью исправления, приёмка и CI здесь не заявлены.
