# WMS-663: минимальное восстановление C7 после чужого exemplar_id

Разработчик Sol 6.1 исполняет прямое ограниченное поручение владельца без skills и дополнительных агентов. Прочитаны локальный AGENTS.md, свежий origin/etalon:AGENTS.md после fetch, требования WMS-663 и `wms663-residual-behavior-testwriter-handoff-20261006.md`. Работа продолжает существующий кандидат без rebase. База до правки — `aa57886772d746d0a08341867d8828bf3ed84d5a`, включая отдельное изменение layout другим разработчиком. Frozen RED до кода — `d66c59a8a13b7053c88680745f10ea07d4d015e2`.

## Причина и изменение

До правки адресный frozen C7 воспроизведён: 1 FAIL / 6.07 s. После чужого STATUS сохранённый snapshot содержал 81/82/99981. Следующий полный корректный STATUS 81/82 давал stored state accepted, но view state unknown: чужой ID стал частью ожидаемого состава.

В существующем `resume_exemplar_document_check` изменено только объединение STATUS со snapshot. Свежие значения обновляют только уже известные пары product_id/exemplar_id; чужие товары и экземпляры не добавляются в сохранённый состав. Существующие данные отсутствующих в частичном STATUS экземпляров и поля, пропущенные ответом, сохраняются. Полный raw STATUS по-прежнему проходит прежнюю классификацию и сохраняется в last_status. Проверки выбора, version/checkpoint, posting/tenant/seller, признаки требований и механизм SET не менялись. Поэтому чужой ответ не принимает целевой выбор, а следующий полный корректный STATUS завершает проверку без повторной записи. Проверка полноты для текущего отображения F4-R не ослаблена.

Новых cache/schema/таблиц/архитектуры нет. Владение этого прохода — только `backend/app/services/ozon_exemplar_documents_service.py` и данный handoff. Тесты, требования, frontend, checker, workflow и чужие изменения не редактировались.

## Проверка после правки

Из backend выполнен один ограниченный прогон с одним worker и изолированным SQLite:

```sh
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR PYTHONDONTWRITEBYTECODE=1 \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  tests/test_wms663_residual_behavior_contract.py \
  tests/test_wms663_partial_accepted_status.py \
  tests/test_wms663_accepted_current_status.py \
  tests/test_wms663_accepted_read_regressions.py \
  -k 'not real_component_label' -n 1 -q --tb=short
```

Результат: **44 PASS / 9.37 s, exit 0, без skips**. Все восемь новых backend-случаев включены. C7 проверяет сохранённый выбор после чужого ответа, успешное восстановление и ровно один SET, затем только STATUS. Смежные F4-R подтверждают unknown при пропущенном товаре/экземпляре и accepted при полном здоровом ответе; current-status/accepted-read защищают текущее отображение, явное следующее действие, stale version и сохранность нового выбора. DOM bridge `real_component_label` исключён из backend-прогона по границе поручения. Восемь ранее прошедших UI-тестов не повторялись; исторические полные наборы не запускались.

`ruff check .` — PASS. `mypy .` — PASS, 552 source files. `git diff --check` — PASS. Diff frozen residual backend-теста относительно d66c59a8a пуст.

PostgreSQL/shared DB/new cluster, Mac browser, секреты, live writes, внешние API/печать, Telegram, merge и deploy не использовались. Транспорт тестов подменён; внешнего результата Ozon эти проверки не доказывают.

## Передача ведущему

Этот результат закрывает новый локальный RED C7 в сохранённой проверке. Независимое ревью и приёмка разработчиком не объявляются. По поручению владельца ведущий передаёт совокупное изменение C7 + layout aa5788677 независимой Astra high один раз. Точный SHA коммита и подтверждение публикации сообщаются после commit/push; данный документ не ссылается на собственный будущий SHA. Посторонние изменения checker/contract-corrections, появившиеся во время работы, остаются у их исполнителя и в этот коммит не включаются.
