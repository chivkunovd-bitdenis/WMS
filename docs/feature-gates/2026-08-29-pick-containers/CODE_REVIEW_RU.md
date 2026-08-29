# Повторный Code Review: PICK-CONTAINERS-01

Повторно проверена только карточка `PICK-CONTAINERS-01`: общий построитель мест
подбора, новая верхняя часть `warehouse_map_service.py` с разрешением путей
тары, два сервиса подбора, два API-сериализатора и три заявленных тестовых
файла. Параллельные изменения в `backend/app/api/warehouses.py` и нижней части
`warehouse_map_service.py` вокруг sorting tree в review не входят и не
оценивались. Production-код reviewer не менял.

## Результат rework

Оба finding предыдущего review закрыты.

### MEDIUM-1 — закрыт

- Marketplace unload HTTP-тест создаёт реальный короб на палете и проверяет
  полный путь `pallet -> box`, включая `kind`, строковые UUID `id`, `code` и
  `label` (`backend/tests/test_marketplace_unload_address_storage.py:182-264`).
- FBS HTTP-тест создаёт реальное грузоместо на палете и проверяет полный путь
  `pallet -> cargo_place` с теми же четырьмя полями
  (`backend/tests/test_fbs_pick_options.py:168-258`).
- Оба теста сравнивают весь объект места целиком. Тем самым они закрепляют шесть
  прежних полей и их значения одновременно с новым `sources`, а два независимых
  API-сериализатора реально проходят непустой `container_path`.

### MEDIUM-2 — закрыт

- Общий helper-тест теперь создаёт отдельный остаток прямо на палете и проверяет
  одноэлементный путь `pallet`; отдельно проверяет `pallet -> box` и
  `pallet -> cargo_place`
  (`backend/tests/test_pick_option_container_sources.py:91-250`).
- Невалидная тара теперь проводится через
  `list_pick_option_locations`: ссылки на тару другого склада и другого tenant
  завершаются `PickOptionLocationError("invalid_container_reference")`, а не
  превращаются в россыпь
  (`backend/tests/test_pick_option_container_sources.py:259-370`).
- Оба внешних endpoint имеют отрицательный HTTP-сценарий и возвращают `409` с
  кодом `invalid_container_reference`: FBS —
  `backend/tests/test_fbs_pick_options.py:426-473`, marketplace unload —
  `backend/tests/test_marketplace_unload_address_storage.py:306-323`.
  Различие формы тела сохранено в рамках существующих API-конвенций: FBS
  использует общий error envelope в `detail`, marketplace unload — строковый
  `detail`; статус и машинный код совпадают.

## Повторно подтверждённый контракт

- У обоих endpoint одинаковая добавочная структура `sources`; старые
  `storage_location_id`, `location_code`, `quantity`, `reserved`, `available` и
  `picked` не удалены и не переименованы.
- Количества места по-прежнему агрегируются по product + storage location, а
  количества физических источников не подменяют `reserved`, `available` и
  `picked`.
- Поддержаны палета, сквозные и приёмочные короб/грузоместо, полный путь
  родительской палеты, россыпь и подпись `Без ячеек` вместо `__SORTING__`.
- Разрешение тары ограничено tenant и складом документа и работает fail-closed.
- Ячейка с нулевым остатком после подбора остаётся в ответе с прежними числами и
  пустым `sources`.
- Frontend в текущем рабочем дереве не изменён.

## Разрешённые проверки

Команды были повторены после rework:

- `pytest -q tests/test_pick_option_container_sources.py tests/test_fbs_pick_options.py tests/test_marketplace_unload_address_storage.py` — не дошёл до collection;
- `ruff check .` — не дошёл до проверки проекта;
- `mypy .` — не дошёл до проверки типов проекта.

Во всех трёх случаях причина внешняя к карточке: синтаксическая ошибка
`parameter without a default follows parameter with a default` в параллельно
изменяемом `backend/app/api/warehouses.py:331-332`. Этот файл reviewer не
исправлял и не считает finding карточки. Полный pytest, npm и Playwright не
запускались согласно ограничению задачи. После завершения параллельной правки
разрешённые три команды нужно повторить, чтобы получить фактический зелёный
результат; текущий review не выдаёт его за выполненный.

## Findings

Новых findings в пределах `PICK-CONTAINERS-01` не обнаружено.

## Verdict

`CODE_REVIEW_PASSED`

Оба замечания предыдущего review закрыты кодом тестов и проверяемыми
утверждениями. Во время reviewer-run фактический запуск проверок был внешне
заблокирован незавершённым параллельным изменением `warehouses.py`; результат
обязательного повторного запуска после изоляции scoped commit зафиксирован ниже.

## Post-review verification scoped commit

После создания scoped commit оркестратор временно сохранил отдельно только два
чужих незавершённых файла, повторил проверки на точном содержимом коммита и
сразу восстановил чужой diff. Итоговые фактические результаты:

- три разрешённых pytest-файла: `10 passed in 12.54s`;
- `ruff check .`: `All checks passed!`;
- `mypy .`: `Success: no issues found in 388 source files`.

Полный pytest, npm и Playwright не запускались. Эти результаты снимают внешний
verification blocker, описанный выше; verdict остаётся `CODE_REVIEW_PASSED`.
