# WMS-663: F1-R, передача разработчика

06.10.2026. Замена разработчика 47956 по поручению владельца. Основание:
`docs/reviews/wms663-astra-6ce78bc.md`. origin/etalon обновлён, правила прочитаны.
Тестовый RED опубликован до правки продукта:
`4d2dd06ff8646c0468745ad5a93228011a1ee720`; HEAD и remote сверены.
Передача тестировщика: `wms663-f1r-testwriter-handoff.md`, 3 FAIL / 5 PASS.
Собственный повтор до правки также дал 3 FAIL / 5 PASS.

Изменён только `backend/app/services/ozon_exemplar_documents_service.py`.
Классификатор сохраняет accepted как завершение конкретной операции,
обновляя status/last_status без сравнения с историческим выбором.
Свежий снимок продолжает обновляться; choice/choices сохраняются как история.
История accepted не накладывается ни на экран, ни на следующую запись
документа/КИЗ. Новый claim задаёт preparing и новый выбор, поэтому строгая
проверка текущего незавершённого намерения сохраняется. Исправлен общий
GET/resume/classifier, а не только document_view.

Ошибка чтения и ответ другого отправления не отменяют завершённую запись;
конкретная ошибка сохраняется, неверный снимок не применяется.
accepted относится к завершённой операции, не подтверждает последующие
изменения кабинета. Текущий status остаётся отдельным полем; существующий
update_not_available по-прежнему запрещает изменение. Новых полей нет.
Защиты unknown, активного writer, версии, tenant, потерянного SET и
разрешённого продолжения последовательных подтверждённых КИЗ не изменены.

Проверка из backend, инструменты постоянного WMS/backend/.venv:

```sh
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  tests/test_wms663_accepted_read_regressions.py \
  tests/test_wms663_astra_regressions.py \
  tests/test_wms663_customs_documents_contract.py \
  tests/test_ozon_fbs_process_contract.py tests/test_fbs_ozon_lane.py \
  tests/test_ozon_box_assembly.py tests/test_ozon_fbs_openapi_models.py \
  -n 1 -q --tb=short
```

**131 passed, 1 skipped, 12 warnings in 17.89s**:
8 новых + 22 предыдущих + 101 соседний тест. SKIP — PostgreSQL-гонка;
PostgreSQL здесь не использовалась. Новая гонка запоздавшего GET против
нового claim прошла с двумя настоящими SQLite-сессиями. Тесты не изменены.

Разовая проба настоящих сервисов на отдельной SQLite также PASS:
принять A, изменить кабинет на LATEST/LATEST-RNPT, последовательно читать
update_available, update_not_available, validation_in_process, future_status,
ship_available. Проверены accepted, сохранение choices и свежих значений;
editable=false только при update_not_available. Ошибка fake_read_failure
и ответ OTHER-POSTING сохраняют accepted, прежний свежий снимок и историю,
показывают конкретную ошибку. На всём цикле ровно один SET. Отдельный файл
теста не создавался; проба не объявляется постоянной защитой.

`ruff check .` — PASS; `mypy .` — PASS, 552 файла; `git diff --check` — PASS.
Все provider-вызовы фиктивные, БД изолированы. Полный CI не запускался.
Нужно новое независимое ревью опубликованного исправления, приёмка и CI.
Предыдущее FAIL и незакрытые доказательства приёмки этим не заменяются.
Браузер, DOM, реальный Ozon и выпуск не проверялись. Навыки и дочерние
агенты не запускались. Чужая работа сохранена; коммит содержит только
сервис и эту передачу. Секреты, кабинеты авторизации, production и Telegram
не использовались. Merge/deploy не выполнялись.
