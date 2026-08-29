# BA-карточка: физическое место товара в подборе

Карточка одна: отгрузка на маркетплейс и FBS меняют один и тот же
пользовательский смысл места подбора и должны сохранить одинаковую форму
ответа. Разделение на две карточки создало бы две конкурирующие трактовки одной
складской структуры и пересекающиеся изменения контрактов и тестов.

```yaml
feature_id: PICK-CONTAINERS-01
title: "Подбор показывает тару и полный путь физического места товара"
source_task: >-
  Только backend. Расширить место в pick-options отгрузки на маркетплейс и FBS
  данными из inventory_balances.container_kind/container_id, чтобы оператор
  видел не только ячейку, но и палету, короб или грузоместо, включая вложенность;
  россыпь обозначать явно, служебный код __SORTING__ заменять на «Без ячеек»,
  существующие поля ответа не удалять и не переименовывать.
business_goal: >-
  Не отправлять сотрудника к одной ячейке без указания физического источника.
  Подбор и карта склада должны одинаково отвечать на вопрос, где именно лежит
  товар, чтобы оператор снял его из правильного короба, грузоместа, с палеты или
  россыпью и не создал фактическое расхождение остатков.
warehouse_user:
  - "Администратор фулфилмента, выполняющий подбор отгрузки на маркетплейс"
  - "Сотрудник фулфилмента с правом отгрузок на маркетплейс"
  - "Администратор фулфилмента или сотрудник с правом упаковки, выполняющий FBS-подбор"
real_world_scenario: >-
  Один SKU может лежать россыпью в ячейке, в коробе, в грузоместе или в коробе
  на палете. Оператор открывает подбор и по каждой строке места видит физический
  источник товара и его адрес: сначала ячейку либо «Без ячеек», затем палету,
  затем конечную тару. Например, короб на палете не превращается в отдельный
  короб без родителя, а товар без тары честно обозначается как лежащий россыпью.
current_problem: >-
  Оба get_pick_options читают агрегат product+storage_location через
  list_location_balances_for_products_in_warehouse. Он складывает все строки
  inventory_balances одной ячейки и не возвращает container_kind/container_id.
  Поэтому текущие PickOptionLocation и API-модели содержат только
  storage_location_id, location_code, quantity, reserved, available и picked:
  товар из короба показывается как товар непосредственно в ячейке, разные
  физические источники в одной ячейке теряются, а наружу может выйти код
  __SORTING__.
target_process:
  - "Источником факта физического размещения остаётся inventory_balances: пустая пара container_kind/container_id означает россыпь, заполненная пара — конкретную тару."
  - "Каждое различимое физическое место товара представлено в pick-options без слияния разных коробов, грузомест, палет и россыпи только потому, что у них одна storage_location_id."
  - "Для тары возвращается её человеческий вид и номер по тем же правилам, что использует GET /warehouses/{id}/map: «Палета», «Короб», «Грузоместо», без сырого UUID вместо номера."
  - "Если конечный короб или грузоместо находится на палете, ответ сохраняет порядок вложенности ячейка -> палета -> короб/грузоместо -> товар."
  - "Если тара не привязана к обычной ячейке и остаток хранится в системной sorting-ячейке, место остаётся в выдаче, но верхний адрес называется «Без ячеек»; __SORTING__ наружу не передаётся."
  - "Если container_kind и container_id отсутствуют, место явно обозначается как «Россыпью» и не получает вымышленную тару."
  - "Одинаковая семантика места действует в GET /operations/marketplace-unload-requests/{request_id}/pick-options и GET /operations/fbs-supplies/{supply_id}/pick-options."
  - "Поля storage_location_id, location_code, quantity, reserved, available и picked сохраняют имена и прежний смысл; новые сведения только добавляются."
screen_or_flow: >-
  ФФ -> Отгрузка на маркетплейс -> Подбор и ФФ -> FBS -> поставка -> Подбор;
  backend-контракты двух pick-options, без изменения frontend в этой карточке.
primary_action: >-
  Открыть подбор и прочитать для товара точное физическое место, откуда его
  нужно снять.
secondary_actions:
  - "Сопоставить место с той же структурой в разделе склада «Ячейки»/карте склада."
  - "Продолжить существующий подбор по прежним количественным полям без изменения их названий."
required_visible_data:
  - "Верхний адрес: код обычной ячейки либо точная подпись «Без ячеек»."
  - "Признак «Россыпью» для остатка без container_kind/container_id."
  - "Для тары: вид «Палета», «Короб» или «Грузоместо» и её человеческий номер."
  - "Для вложенной тары: родительская палета и конечный короб/грузоместо в порядке от внешнего объекта к внутреннему."
  - "Все прежние поля места: storage_location_id, location_code, quantity, reserved, available, picked."
explicitly_unnecessary_data:
  - "Изменения frontend, его типов, вёрстки, подписей, иконок или сценариев."
  - "Изменение команд снятия, сканирования, отмены, движений остатков или фиксации container_id в факте подбора."
  - "Новый источник правды рядом с inventory_balances или отдельная копия складской иерархии."
  - "Посторонний состав контейнера: ответ нужен только для товаров текущего документа подбора."
  - "Переименование или удаление существующих полей и endpoint."
success_state: >-
  Оба внешних HTTP endpoint сериализуют для реального остатка в таре непустой
  sources[].container_path. Каждый элемент пути содержит kind, id, code и label,
  а id выходит как строковый UUID. Общий построитель подтверждает три отдельных
  случая: товар прямо на палете даёт путь Палета; товар в коробе на палете даёт
  путь Палета -> Короб; товар в грузоместе на палете даёт путь Палета ->
  Грузоместо. Россыпь имеет явный признак без тары, sorting-зона называется
  «Без ячеек». В ответах обоих endpoint одновременно присутствуют все шесть
  прежних полей места с прежними значениями для соответствующего исходного
  остатка.
error_state: >-
  Существующие ошибки доступа, отсутствующего документа и недоступного статуса
  не меняются. Если строка остатка заявляет тару, но её нельзя безопасно
  разрешить в пределах того же tenant и склада, сервер не должен выдавать её за
  россыпь или подставлять чужую тару; это неконсистентные складские данные, а не
  нормальное пустое место.
empty_state: >-
  Документ без плановых товаров по-прежнему получает пустой список. Плановый
  товар без положительного остатка остаётся в выдаче с пустым списком мест, как
  в текущем контракте. Остаток в sorting-зоне не считается пустым и не исчезает.
roles_permissions:
  - "Отгрузка на маркетплейс: fulfillment_admin и fulfillment_staff с разрешением mp_shipments; fulfillment_seller по-прежнему не допускается к исполнительскому pick-options."
  - "FBS: fulfillment_admin и fulfillment_staff с разрешением packaging через существующий require_fbs_operator_access."
  - "Расширение ответа не расширяет текущие роли и права."
tenant_seller_warehouse_scope: >-
  Документ, остаток, ячейка, палета, короб и грузоместо разрешаются только внутри
  user.tenant_id и склада документа. В ответ не попадают остатки другого tenant,
  другого склада или товары вне плана текущей отгрузки/FBS-поставки.
external_dependencies:
  - "Текущие inventory_balances с container_kind/container_id."
  - "Текущие модели Pallet, WarehouseBox, InboundIntakeBox и InboundIntakeCargoPlace, из которых warehouse_map_service получает человеческие коды и parent pallet."
  - "SORTING_LOCATION_CODE и UNASSIGNED_LABEL из sorting_location_service."
  - "Внешние API маркетплейсов и новые секреты не нужны."
business_assumptions:
  - "Два endpoint входят в одну атомарную карточку, потому что пользователь требует общую форму и одинаковые слова, а построение места и регрессионные случаи пересекаются."
  - "«Номер тары» означает тот же человеческий code, который карта склада показывает для соответствующей модели, а не UUID и не произвольный новый номер."
  - "«Россыпью» — это состояние конкретного остатка без тары; «Без ячеек» — верхний адрес sorting-зоны. Эти признаки не заменяют друг друга и могут сочетаться."
  - "Карточка расширяет только чтение pick-options; корректировка container-aware списания является отдельным поведением и в исходной задаче не запрошена."
test_expectations:
  - "GET /operations/marketplace-unload-requests/{request_id}/pick-options создаёт реальный остаток в таре и проверяет непустой sources[].container_path[] целиком: kind, строковый UUID id, человеческие code и label; в том же объекте проверяются прежние storage_location_id, location_code, quantity, reserved, available и picked."
  - "GET /operations/fbs-supplies/{supply_id}/pick-options создаёт реальный остаток в таре и проверяет тот же непустой JSON container_path и те же шесть прежних полей; хотя бы один из двух HTTP-тестов обязан пройти вложенный путь из двух элементов."
  - "Общий pick-service отдельными положительными сценариями покрывает прямую палету, pallet -> box и pallet -> cargo_place с правильным порядком и человеческими названиями."
  - "Неконсистентный InventoryBalance с отсутствующей или чужой тарой проходит через общий list_pick_option_locations и обязан завершиться PickOptionLocationError, а не превратиться в россыпь."
  - "Неконсистентная ссылка на тару также проверяется через внешний HTTP-контракт обоих pick-options: endpoint не отвечает 200 с успешной россыпью; осознанный статус ошибки фиксируется тестом и остаётся согласованным между двумя ответами либо различие документируется явно."
open_questions:
  - >-
    Точные технические имена и вложенная JSON-форма новых добавочных полей не
    заданы пользователем. Это не блокирует BA: Product/Dev должны выбрать один
    общий добавочный контракт для обоих endpoint, который однозначно передаёт
    перечисленные видимые данные и не меняет шесть существующих полей.
ba_agent: "/root/ba_pick_containers"
product_agent: "/root/product_before_pick_containers"
dev_agent: "/root/dev_pick_containers"
code_review_agent: "/root/review_pick_containers"
product_browser_agent: "/root/product_browser_pick_containers"
changed_files:
  - "docs/feature-gates/2026-08-29-pick-containers/FEATURE_CARDS_RU.md"
  - "backend/app/services/warehouse_map_service.py"
  - "backend/app/services/pick_option_location_service.py"
  - "backend/app/services/marketplace_unload_pick_service.py"
  - "backend/app/services/fbs_picking_service.py"
  - "backend/app/api/marketplace_unload_requests.py"
  - "backend/app/api/fbs_supplies.py"
  - "backend/tests/test_pick_option_container_sources.py"
  - "backend/tests/test_fbs_pick_options.py"
  - "backend/tests/test_marketplace_unload_address_storage.py"
tests_run:
  - "До rework: три точечных pytest-файла — 9 passed; ruff check . и mypy . были зелёными. После rework этот результат не считается проверкой нового patch."
  - "cd backend && /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check app/api/marketplace_unload_requests.py tests/test_pick_option_container_sources.py tests/test_fbs_pick_options.py tests/test_marketplace_unload_address_storage.py — All checks passed."
  - "На точном содержимом scoped commit, при временно сохранённом отдельно чужом diff: cd backend && /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q tests/test_pick_option_container_sources.py tests/test_fbs_pick_options.py tests/test_marketplace_unload_address_storage.py — 10 passed in 12.54s."
  - "На том же содержимом: cd backend && /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check . — All checks passed."
  - "На том же содержимом: cd backend && /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m mypy . — Success: no issues found in 388 source files."
  - "Полный pytest, npm и Playwright не запускались по явному ограничению карточки."
commit_or_patch_ref: "Git commit; итоговый SHA фиксируется в handoff после amend"
blocking_issues: []
status: DEV_DONE
```

**BA verdict: `BA_READY`.** Продуктовый результат и границы заданы; открытым
остаётся только техническое именование добавочных полей, которое не меняет
складской сценарий и должно быть единым для двух ответов.

## Rework history

- 29.08.2026, после `CODE_REVIEW_FAILED`: BA-критерии уточнены обязательными
  HTTP-проверками непустого `container_path` для обоих endpoint, отдельными
  путями `pallet`, `pallet -> box`, `pallet -> cargo_place` и fail-closed
  проверками общего pick-service и внешнего API. Бизнес-границы карточки не
  изменены; статус возвращён в `BA_READY` для повторного Product/Dev-цикла.
- 29.08.2026, повторный Atomic Dev: MP HTTP-тест получил реальный путь
  `pallet -> box`, FBS HTTP-тест — `pallet -> cargo_place`; оба проверяют
  непустой JSON со всеми `kind/id/code/label` и шестью прежними значениями.
  Общий helper дополнительно покрыт прямой палетой, вложенным грузоместом и
  ошибками чужого tenant/склада через `list_pick_option_locations`. Оба endpoint
  фиксируют `409 invalid_container_reference`; MP сохраняет простой исторический
  `detail`, а FBS — существующий FBS error envelope с тем же кодом.
- 29.08.2026, post-review verification: чужой diff двух файлов был временно
  сохранён отдельным Git stash, все ворота прошли на точном scoped commit, после
  чего чужой diff восстановлен без включения в коммит.
