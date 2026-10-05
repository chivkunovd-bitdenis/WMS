# WMS-517: легитимная миграция трёх проверок цены — ожидает Astra high

Независимый замещающий тестировщик Sol6.1 high, явная замена session57763.
Основание до правок: [заключение отдельного аналитика](2026-10-06-wms517-legacy-analyst.md),
сохранённое в `6b85381722dafb690c3a2c4b90cce762b4b3643b`, и актуальные R18–R24.
Это исполнение разрешённой миграции источника, не самостоятельная отмена требований
и не приёмка реализации. SKILL.md не читались, вложенные агенты не запускались.

Базовый SHA fixture adapter: `5544027611f3ec181ad62233c0838d58fedbb46c`.
Product code developer517 по-прежнему не staged тестировщиком. Его dirty код —
среда нижеописанных запусков; SHA контракта не выдаётся за SHA готовой реализации.

## Точные изменения разрешённого контракта

1. `test_create_reload_and_overlap_resume_without_duplicate`: заменена только
   обязательность старого `price_snapshot_id` на чтение сохранённого `wb_sale`
   новой DB-сессией. Проверяются source/order_id/srid/saleID, исходная максимальная
   finishedPrice, обе даты, raw_sale, received_at, complete, две страницы и одна
   строка. Прежний точный max product_cost, один operation/item, тот же request,
   перекрывающие claims, mismatch и чужой seller остались.
2. `test_registry_missing_price_is_an_actual_local_error`: HTTP S-sale получает
   `finishedPrice=null`, а старый RUB snapshot заведомо валиден (`12345`). Реестр
   по-прежнему обязан показать `error`; код ошибки заменён с legacy
   `missing_rub_final_price` на фактический `invalid_sale_price`. Валидный старый
   snapshot не может спасти отсутствующую цену продажи. Дополнительный отдельный
   файл проверяет противоположное направление: отсутствующий/нерублёвый старый
   snapshot не блокирует валидную точную S-sale.
3. `test_retry_retains_old_price_error_and_new_attempt`: первый полный HTTP отчёт
   содержит null finishedPrice; следующий полный отчёт — `123.45` и свежую дату.
   Старые WMS snapshots валидны и отличаются (`77700`, затем `88800`), поэтому
   не способны выдать требуемые `12345` копеек. Первая попытка остаётся failed с
   прежней ошибкой и неизменным sales evidence. Retry даёт attempt=2, cost=12345,
   document_id=None, снимает старую claim и сохраняет ровно одну новую. Сравнение
   old/new legacy snapshot id заменено проверкой сохранности старого evidence и
   точности нового. Повтор expected_attempt=1 не создаёт третью попытку.

Дополнительный файл `backend/tests/test_wms517_legacy_price_source_contract.py`
содержит два положительных случая отсутствующего/нерублёвого старого snapshot.
Удаление отсутствующего снимка касается только свежесозданных fixture-данных
до создания withdrawal items; production и чужие данные не затронуты.

AST сравнение с adapter SHA: весь ledger за исключением ровно трёх перечисленных
test functions идентичен. Остальные 21 test functions, все исходные имена,
параметры и decorators сохранены. Шесть consumers по-прежнему идентичны исходному
AST за исключением import общей fixture. Исходные sales 51+6 и SC7 неизменны.

## Отрицательное доказательство и выполнение

В `backend/tests/wms517_price_source_negative_control.py` сохранён воспроизводимый
диагностический запуск F1/F3. Он извлекает только эти текущие функции из AST,
создаёт временный probe внутри постоянного checkout и удаляет его после запуска.
Подмена касается только HTTP ответа supplier/sales: finishedPrice намеренно null.
Private product helpers, admission, pricing, claims/recovery не заменяются.
Диагностика не входит в обычный pytest discovery и не меняет ожидания этих функций.

Команда из backend:

`PYTHONDONTWRITEBYTECODE=1 /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python tests/wms517_price_source_negative_control.py`

Окончательный отрицательный результат: **2 failed**, 6 warnings, 1.13s,
оба бизнес-assert, без collection/setup errors. F1 получил None вместо максимальной
стоимости; F3 получил None вместо 12345 при attempt=2. Runner завершился exit0
с `NEGATIVE CONTROL VERIFIED`: именно эти бизнес-падения являются ожидаемым
результатом отрицательной проверки. Первый черновой runner с wildcard import
ошибочно собрал соседние тесты и не импортировал приватные fixture-данные;
этот запуск не считается доказательством. До коммита исправлены только его импорты.

Обычный общий запуск из backend:

`PYTHONDONTWRITEBYTECODE=1 /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q tests/test_withdrawal_ledger.py tests/test_wms517_legacy_price_source_contract.py tests/test_withdrawal_review_fixes.py tests/test_withdrawal_orchestration.py tests/test_withdrawal_row_status.py tests/test_withdrawal_readiness.py tests/test_withdrawal_access.py tests/test_withdrawal_wms563.py --tb=line -p no:cacheprovider`

Результат: **135 passed, 4 skipped**, 6 warnings, 11.52s, без deselection.
Четыре PostgreSQL-only проверки не выполнялись; кластер56517 разработчика не
затрагивался. Физическая подпись/production/маркетплейсы не проверялись.

## Независимое ревью ещё не выполнено

**REVIEW_PENDING.** Ведущий должен передать этот отдельный commit и ledger
независимому Astra high. Его заключение сюда не подменяется собственным PASS.
Успешный pytest — факт исполнения, не разрешение объявить correction или WMS-517
принятой. Новый partial/Decimal frozen contract остаётся RED (4 failed/14 passed)
до product fixes, затем отдельное ревью, приёмка и CI точного product SHA.
