# Выкладка 27 сентября 2026

Файл нужен для итоговой сверки: какие задачи в этот день уже ушли на прод и какие
выкладываются пакетом PSP-2, чтобы отдельный агент мог собрать всё вместе и проверить,
не затёрли ли мы что-то при сведении. Ведётся ведущим пакета PSP-2 (Claude), обновляется
по мере сведения и выкладки.

## 1. Точка отсчёта: что стоит на проде

Проверено 27.09.2026 в 22:50 по Тбилиси (18:50 UTC), боевой сервер только читался.

- Прод `/opt/wms` = ветка `etalon`, коммит **`a26bc913`** («Merge pull request #278 … wms557-fbs-box-remaining», 22:36 +04). Совпадает с `origin/etalon`.
- Незакоммиченных изменений в `/opt/wms` нет; контейнеры `wms_prod-*` работают.
- За день прод обновляли только из `origin/etalon` (reflog `/opt/wms`: сбросы на origin/etalon в 14:49–18:36 UTC). Правок, которых нет в etalon, на проде нет.

Вывод для выпуска PSP-2: ветки пакета собраны от старого etalon **`141c9fb9`** (26.09).
Выпуск собирается в ветке **`release/psp2-20260927`** от текущего `origin/etalon` (`a26bc913`),
каждая ветка задачи вливается поверх него. Ничего не откатывать, при конфликте сохранять
обе стороны; изменения, уже выкаченные сегодня (раздел 2), не терять.

## 2. Уже выкачено на прод 27.09 другими сессиями (между 141c9fb9 и a26bc913)

Это НЕ задачи пакета PSP-2 — список нужен, чтобы при сведении их не затереть.

| Время (+04) | Коммит | Что |
|---|---|---|
| 17:31 | `4f2b8883` | PR #270 — WMS-537, стикер WB в поставке-черновике (fix/wms537-draft-supply-stickers) |
| 18:49 | `33dfce7f` | PR #271 — WMS-550, скан в сортировке (codex/wms550-sorting-scan) |
| 19:02 | `a4d7f33e` | PR #272 — WMS-550 (продолжение) |
| 19:22 | `c18df7fb` | PR #273 — WMS-550 (продолжение) |
| 19:43 | `b344a00a` | PR #274 — WMS-550 (продолжение) |
| 20:37 | `ab432224` | PR #275 — WMS-550 (продолжение) |
| 20:55 | `7e481a80` | PR #276 — WMS-550 (продолжение) |
| 22:18 | `de0be833` | PR #277 — WMS-556, вывод из оборота Горячкиной (codex/wms556-goryachkina-withdrawal-gate) |
| 22:20 | `3a36ce89` | WMS-556, ops — seller-scoped signing process |
| 22:36 | `a26bc913` | PR #278 — WMS-557, остаток в коробах FBS (codex/wms557-fbs-box-remaining) |

Номера задач в сообщениях этих коммитов: WMS-517, 537, 550, 551, 552, 553, 554, 555, 556, 557, 558.

## 3. Пакет PSP-2 — задачи этой выкладки

Постановка владельца 27.09.2026 (голосом). Требования и приёмка — `docs/requirements/WMS-NNN.md`
в ветке каждой задачи. Разработка — Sonnet, перекрёстное ревью — Astra, приёмка — аналитик задачи.
SHA — вершина ветки задачи на момент записи; итоговые SHA вливания в `release/psp2-20260927`
дописываются в раздел 5.

| Задача | Суть | Ветка | SHA | Состояние на 22:50 |
|---|---|---|---|---|
| WMS-491 | Карточка селлера: строка «Селлеры» кликабельна, кнопка «Реквизиты» переехала в карточку; реквизиты, выставленные счета, «Товары» (каталог с фильтром селлера), «Выставить счёт» («Расчёты» с фильтром селлера) | `feat/wms491-seller-card` | `7cdbf149` | ревью Astra принято (3 круга), идёт приёмка |
| WMS-547 | Реквизиты селлера по API WB/Ozon: ИНН и наименование, КПП через DaData; автозаполнение пустых при подключении ключа; кнопки «Заполнить из WB / из Ozon» | `feat/wms547-seller-requisites-api` | `fb365975` | ревью принято (2 круга), идёт приёмка. Содержит WMS-491 — вливать после неё |
| WMS-497 | Печатный лист инвентаризации: шапка (номер, создатель, дата, фильтры), таблица с зеброй — ШК, артикул, название, всего, в резерве, пустой «Факт» | `feat/wms497-inventory-print-sheet` | `d537c1bd` | ревью принято (4 круга), идёт приёмка. Миграция `20260927_0497`. **Зависит от WMS-530** (база ветки — etalon + 530) |
| WMS-549 | «Расчёты» в кабинете селлера: только свой селлер (изоляция на сервере), вкладки «Начисления» / «Выставленные счета» / «Ставки»; у ФФ экран не меняется. Попутно исправлен прод-баг ФФ: «Загрузить ещё» в истории счетов терял счета | `feat/wms549-seller-billing` | `e0c4bbb0` | ревью: всё существенное закрыто (3 круга), идёт приёмка |
| WMS-548 | Выбор товаров при подключении ключа: окно выбора, синхронизация только выбранных, у ФФ только выбранные, у селлера весь каталог и «Добавить к фулфилменту»; снимок Ozon | `feat/wms548-catalog-selection` (+ куски `feat/wms548-d3-ozon-snapshot`, `feat/wms548-d5-seller-catalog-ui`) | `9076b0f7` (+ `bde32da7`, `43bf3f3a`) | ревью №2: осталось F1 (блокировка при двух процессах API), F8/F9 — исправляются. Миграция `20260927_0548` |
| WMS-490 | Полноценная карточка товара: окно из строки каталога; остаток/резерв/доступно; вкладки «Основное», «Движения», «Расположение», «Задать остаток» | `feat/wms490-product-card` (+ `feat/wms490-review1-fixes`, `feat/wms490-d4-movements-tab`) | `540b6064` (+ `0020848b`, `039ca504`) | исправления ревью №1 готовы, нужна короткая перепроверка. **Зависит от WMS-530, 531, 532, 535** |

## 3.1 Досведено 28.09.2026 — WMS-535 и WMS-560

Владелец согласовал выпуск шести задач пакета: WMS-491, WMS-547, WMS-549, WMS-548 (сведены 27.09,
см. раздел 5) и дополнительно WMS-535, WMS-560 — сведены 28.09, туда же в раздел 5.

| Задача | Суть | Ветка | SHA ветки | Состояние |
|---|---|---|---|---|
| WMS-535 | Все штрихкоды размера WB хранятся в одной карточке (новая таблица `product_barcodes`); разовые CLI-команды (дозагрузка ШК на существующих карточках, склейка дублей) в этот сведённый выпуск не запускались — отдельная production-операция после выкладки | `feat/wms535-wb-all-barcodes` | `caa431f9` | принято с оговорками, ожидает production-операций R7/R8. Была также в разделе 4 как зависимость WMS-490 — с этим слиянием она в etalon больше не «зависимость», а часть выпуска |
| WMS-560 | Лента FBS печатает заказ, чей КИЗ WB подтвердил без эха (`wb_pending_confirmation`, путь WMS-529): раньше такой заказ выпадал из печати. Повод — AVpack 27.09: из 13 заказов в ленту попали 4, остальные 9 WB подтвердил через минуту | `fix/wms560-tape-pending-kiz` | `f3964702` | сделано в ветке, тесты зелёные, без отдельного аналитика и перекрёстного ревью (прямое указание владельца) |

Ветка WMS-560 несла собственный файл сверки `docs/VYKLADKA-2026-09-27.md` (независимая сессия,
подтвердила те же факты по прод-состоянию a26bc913 и по выкаткам дня, что и раздел 1–2 этого файла;
дополнительно уточнила: 27.09 14:49 на прод ушёл WMS-537, реальный список коммитов WMS-550 занял
PR #271–276, реестр подготовленных-но-не-выложенных задач WMS-546/WMS-561). Его содержимое сведено
сюда, отдельный файл `docs/VYKLADKA-2026-09-27.md` удалён — файл выкладки один: этот.

## 4. Зависимости пакета, которых нет в etalon

| Задача | Ветка | SHA | Состояние |
|---|---|---|---|
| WMS-530 / WMS-532 | один остаток во всей системе; каталог «Остаток / Резерв / Доступно» | `feat/wms530-single-stock` | `107fbb3c` | реализовано, приёмки не было — нужна для WMS-497 и WMS-490 |
| WMS-531 | отчёт «Остатки и движения», каждое движение по документу строкой | `feat/wms531-report-xlsx` | `f6255182` | два круга ревью Astra, приёмки не было — нужна для вкладки «Движения» WMS-490 |

## 5. Сведение и выкладка

Заполняется по мере работы: что влито в `release/psp2-20260927` (SHA слияния, конфликты и как
разрешены), результат CI, SHA выкладки на прод и время. Выкладка — только по команде владельца «кати».

| Шаг | SHA | Примечание |
|---|---|---|
| Ветка выпуска создана от `origin/etalon` | `a26bc913` | 27.09 22:50 |
| `git fetch origin` перед началом | — | `origin/etalon` = `a26bc913`, тот же коммит, что и точка отсчёта; свежих коммитов на проде не появилось, влитие свежего etalon не потребовалось |
| Слияние WMS-491 (`origin/feat/wms491-seller-card`, тип afa6f28c) | `6b7b478f8a84a7462a1f513b0867a47496a0694c` | Конфликтов нет (auto-merge). Ветка на момент слияния ушла дальше SHA из раздела 3 (`7cdbf149` → `afa6f28c`) — добавился только коммит приёмки аналитика поверх принятого ревью, вливалась вершина ветки |
| Слияние WMS-547 (`origin/feat/wms547-seller-requisites-api`, тип a93778b6, содержит WMS-491) | `70dab81c6aa2f9ccf97d9bcf80c27d5919177324` | Конфликтов нет (auto-merge, включая `backend/app/core/settings.py` и `backend/app/main.py`, куда сегодня писал и прод). Точечная проверка: diff между `origin/etalon` и веткой выпуска по всем 119 файлам, изменённым на проде 27.09 (WMS-537/550/556/557), показал различие только в settings.py и main.py — оба различия являются чистыми добавками WMS-547 (роутер, поля настроек), ничего из прод-изменений не потеряно |
| Карточки бэклога | — | В `docs/KANONICHESKIY_BACKLOG.md` добавлены «## WMS-491 …» и «## WMS-547 …» со статусом «ПРИНЯТО С ОГОВОРКАМИ, ВЫПУСК PSP-2» и ссылками на `docs/requirements/WMS-491.md` / `WMS-547.md` |
| Проверки бэкенда | ruff: 24 ошибки — все в `backend/scripts/wms555_reset_artmaks.py`, файл байт-в-байт идентичен `origin/etalon` (не тронут слияниями, привнесён сегодняшним прод-коммитом WMS-555/551, вне зоны этой задачи). mypy: 13 ошибок — там же и в `backend/scripts/artmaks_cell_qr_mapping.py`, тоже идентичен etalon. `pytest -n auto tests/test_seller_marketplace_requisites.py tests/test_seller_requisites_autofill.py tests/test_dadata_party_service.py tests/test_billing_configuration_api.py` — 59 passed. `alembic heads` — одна голова `20260927_0556` | Целевые тесты и миграции зелёные; линт/тайпчек падают только на чужом, не изменённом этой задачей коде |
| Проверки фронтенда | `npx tsc --noEmit -p tsconfig.app.json` — без ошибок. `npm run build` — успешно. `npx vitest run src/screens/v2/SellerCardScreen.dom.test.tsx src/screens/v2/FfProductsCatalogScreen.sellerUrlFilter.dom.test.tsx src/screens/ff/FfBillingScreen.sellerUrlFilter.dom.test.tsx` — 12 passed | node_modules — симлинк на `.worktrees/_psp2-node/node_modules` создан (отсутствовал) |
| `check_task_documents.py origin/etalon` | — | «Документы задач заполнены; AGENTS.md и CLAUDE.md совпадают» |
| Слияние WMS-549 (`origin/feat/wms549-seller-billing`, тип 6e3df900) | `e509677e99f3ccb9bd4940fdf85e985fbe0f4056` | Конфликты в трёх файлах, все — «оба признака одновременно» (совмещение WMS-491/547 и WMS-549): 1) `backend/app/main.py` — оба ветки добавили свою строку `app.include_router(...)` на одном месте (WMS-547 `billing_profile_marketplace_router`, WMS-549 `seller_billing_router`) — оставлены обе. 2) `frontend/src/screens/ff/FfBillingInvoicesPanel.tsx` — WMS-491 добавил проп `fixedSellerId` (панель в карточке селлера), WMS-549 — `sellerScope` (кабинет селлера); оставлены оба пропа, везде, где по одному из них прятались фильтр/колонка «Селлер» (`fixedSellerId ? null : …`, `...(fixedSellerId ? [] : […])`), условие расширено до `fixedSellerId \|\| sellerScope`; `invoiceHistoryEmptyState` вызывается с `sellerScope \|\| Boolean(fixedSellerId)`. 3) `frontend/src/screens/ff/FfBillingScreen.tsx` — импорт `resolveInitialSellerFilter` (WMS-491, URL-фильтр) и импорт `FfBillingSellerRates`/тип `ScreenTab` (WMS-549) объединены; конструктор компонента — совмещены сигнатура `sellerScope = false` (549) и рефы `location`, `searchParams`, `sellerIdAutoAppliedRef`, `sellerFilterOwnCleanupRef`, `sellerFilterFromUrlRef` (491); `SelectInput` «Селлер» — скрытие по `sellerScope` (549) + сброс `sellerFilterFromUrlRef.current = false` при ручном выборе (491, F2). Раздел «Начисления»/вкладка «Ставки» и рендер для ФФ (`tab === 'charges' ? (sellerScope ? … : …)`) слились без конфликта — участок не пересекался с правками WMS-491. Образец разрешения (`origin/mockup/psp2-clickable`, коммит `80abf4c1`) использован только как сверка направления, файлы макета в выпуск не переносились. Сверка по всем 119 файлам прод-изменений 27.09 — различий нет (main.py/settings.py не менялись этим шагом) |
| Побочная находка при тестах | — | `src/screens/ff/FfBillingScreen.sellerScope.test.tsx` — 2 теста падали после слияния: `renderToStaticMarkup(<FfBillingScreen .../>)` без `<MemoryRouter>` перестал работать, так как в объединённом компоненте появился `useLocation()` из WMS-491 (в ветке WMS-549 отдельно его не было). Обёрнуто в `<MemoryRouter>` по образцу соседних тестов этого же файла — правка только тестовой обвязки, поведение компонента не менялось |
| Проверки бэкенда (WMS-549) | `pytest -n auto tests/test_wms549_invoice_pagination.py tests/test_wms549_seller_billing_api.py tests/test_wms549_seller_rates.py tests/test_billing_invoice_v2_api.py tests/test_billing_invoice_api.py` — 38 passed. `alembic heads` — одна голова `20260927_0556` (задача без миграций) | |
| Проверки фронтенда (WMS-549) | `npx tsc --noEmit -p tsconfig.app.json` — без ошибок. `npm run build` — успешно. `npx vitest run src/apps/seller src/screens/ff` — 304 passed, 2 упавших теста (`FfInboundRequestView.test.ts`, лимит размера модуля и multiset testid) — файл байт-в-байт идентичен `origin/etalon`, вне зоны этой задачи | |
| Карточка бэклога | — | В `docs/KANONICHESKIY_BACKLOG.md` добавлена «## WMS-549 …» со статусом «ПРИНЯТО С ОГОВОРКАМИ, ВЫПУСК PSP-2» и ссылкой на `docs/requirements/WMS-549.md` |
| `check_task_documents.py origin/etalon` (повторно, после WMS-549) | — | «Документы задач заполнены; AGENTS.md и CLAUDE.md совпадают» |
| Слияние WMS-548 (`origin/feat/wms548-catalog-selection`, тип 4fe69fb4) | `6e0c229a168abaff0e91c1d631e4ca45ef8fe646` | Один конфликт: `backend/app/main.py` — обе ветки добавили свой импорт роутера на одной строке (WMS-549 `seller_billing_router`, WMS-548 `seller_catalog_router`) — оставлены оба импорта и обе регистрации `app.include_router(...)`. `backend/app/api/wildberries_integration.py` и `ozon_integration.py` слились автоматически без конфликта: вызов `autofill_requisites_after_key_saved` (WMS-547) и фильтр выбранных карточек (WMS-548) оба на месте в wildberries_integration.py; в ozon_integration.py конфликта не возникло, так как ветка WMS-548 этот файл не трогала (ожидание в задаче не подтвердилось при проверке). Сверка по всем 119 файлам прод-изменений 27.09 — различий, кроме чистых добавок PSP-2, нет |
| Alembic — слияние двух голов | новая миграция `20260927_0560_merge_wms548_psp2.py`, `down_revision = ("20260927_0548", "20260927_0556")` | Миграция WMS-548 (`20260927_0548`, `down_revision=20260924_0526`) создала форк с сегодняшней прод-миграцией WMS-556 (`20260927_0556`, тоже потомок `20260924_0526`) — добавлена пустая merge-точка по образцу `20260927_0556_merge_withdrawal.py`. `alembic heads` — одна голова `20260927_0560` |
| Побочная находка при тестах | — | `tests/test_seller_requisites_autofill.py::test_c7_wb_seller_info_failure_does_not_affect_key_save_response` (5 параметризаций) ожидал `products_created=1` при сохранении ключа WB — по новому процессу WMS-548 подключение ключа больше не заводит товары автоматически (заводятся после выбора в отдельном окне), сохранение ключа теперь даёт `products_created=0`. Ожидание в `_EXPECTED_MOCK_CARDS_SAVE_RESPONSE` поправлено на 0, остальные поля и сценарии теста не менялись; сверено с `tests/test_wms548_wb_sync_selection.py`, где то же самое утверждается явно (`products_created == 0` при первом сохранении ключа) |
| Проверки бэкенда (WMS-548) | `pytest -n auto tests/test_wms548_add_to_fulfillment.py tests/test_wms548_ozon_selection.py tests/test_wms548_seller_catalog_page.py tests/test_wms548_wb_sync_selection.py tests/test_seller_requisites_autofill.py tests/test_ozon_product_import.py` — 57 passed. `alembic heads` — одна голова `20260927_0560` | |
| Проверки фронтенда (WMS-548) | `npx tsc --noEmit -p tsconfig.app.json` — без ошибок. `npm run build` — успешно. `npx vitest run src/screens/v2/SellerProductsStockScreen.test.ts src/screens/v2/SellerCatalogSelectionDialog.test.ts` — 46 passed | |
| Карточка бэклога | — | В `docs/KANONICHESKIY_BACKLOG.md` добавлена «## WMS-548 …» со статусом «ПРИНЯТО С ОГОВОРКАМИ, ВЫПУСК PSP-2» и ссылкой на `docs/requirements/WMS-548.md` |
| `check_task_documents.py origin/etalon` (после WMS-548) | — | «Документы задач заполнены; AGENTS.md и CLAUDE.md совпадают» |
| WMS-497, WMS-490 | — | НЕ влиты в этот заход: ждут WMS-530/531 (нет в etalon), по указанию владельца |
| `git fetch origin` перед досведением 28.09 | — | `origin/etalon` по-прежнему `a26bc913`, предок ветки выпуска — влитие свежего etalon не потребовалось |
| Слияние WMS-535 (`origin/feat/wms535-wb-all-barcodes`, тип caa431f9) | `f42b0836871ef7488e033888da4fa30920ddcbea` | Один конфликт: `docs/KANONICHESKIY_BACKLOG.md` — у ветки была своя карточка «## WMS-535» (плюс попутная «## WMS-536», отдельная постановка) — обе добавлены к существующим карточкам, статус WMS-535 дополнен пометкой «ВЫПУСК PSP-2». `backend/app/api/wildberries_integration.py` слился автоматически без конфликта: фильтр выбранных карточек (WMS-548, вокруг вызова upsert) и сам upsert с новой моделью `product_barcode` (WMS-535) не пересеклись построчно. Разовые CLI-команды ветки (`app/cli/backfill_wb_product_barcodes.py`, `app/cli/merge_duplicate_wb_chrt_products.py`) влиты как код, но НЕ запускались — R7/R8 остаются отдельной production-операцией после выкладки. Сверка по 119 файлам прод-изменений 27.09 — различий, кроме чистых добавок PSP-2, нет |
| Слияние WMS-560 (`origin/fix/wms560-tape-pending-kiz`, тип f3964702) | `1146c7d2dc95c4adbbf8691ef6fe3c21d9f27908` | Один конфликт: `docs/KANONICHESKIY_BACKLOG.md` — у ветки была своя карточка «## WMS-560», добавлена к существующим, статус дополнен пометкой «ВЫПУСК PSP-2». Продуктовый код (`fbs_order_tape_print_service.py`) слился автоматически без конфликта — ветка не пересекалась с задачами пакета по файлам. Собственный файл сверки ветки `docs/VYKLADKA-2026-09-27.md` сведён в раздел 3.1 этого файла и удалён (`git rm`) — файл выкладки один |
| Alembic — переслияние трёх голов | старая merge-точка `20260927_0560_merge_wms548_psp2.py` удалена (число «0560» совпадало с номером задачи WMS-560 — переименовано во избежание путаницы), вместо неё `20260927_0561_merge_psp2_heads.py`, `down_revision = ("20260927_0548", "20260927_0556", "20260925_0535")` | Миграция WMS-535 (`20260925_0535`, `down_revision=20260924_0526`) добавила третий форк к тем же двум, что уже сводила `0560`. Одна merge-точка на все три. `alembic heads` — одна голова `20260927_0561` |
| Ruff-фикс WMS-555 (пункт 3 задачи) | `e6e7b94c3f0bf037a9dfe0f99f4e252f70437ff3` | `backend/scripts/wms555_reset_artmaks.py` — 24 ошибки E501 исправлены `ruff format` + разбивкой длинных SQL-литералов на смежные строковые константы (Python/SQL склеивают их в тот же текст). Сверено построчным сравнением AST-строк до/после правки — единственное отличие: пробел после запятой в одном SQL-литерале (на выполнение не влияет). Разовые команды скрипта не запускались. `ruff check .` по всему backend — «All checks passed!» |
| Проверки (28.09, после WMS-535/560/ruff-фикса) | `ruff check .` — все проверки пройдены. `mypy .` — 13 ошибок, все в `backend/scripts/wms555_reset_artmaks.py` (11, отсутствие типовых аннотаций — вне объёма «только форматирование») и `backend/scripts/artmaks_cell_qr_mapping.py` (2, не менялся). `pytest -n auto tests/test_fbs_product_barcode_source.py tests/test_wms535_cli.py tests/test_wms535_product_barcodes.py tests/test_wms560_tape_pending_kiz.py tests/test_fbs_wb_exact_kiz_confirmation.py` — 37 passed, 1 skipped (требует PostgreSQL row locks, локально SQLite). `alembic heads` — одна голова `20260927_0561`. `npx tsc --noEmit` — без ошибок. `npm run build` — успешно. `check_task_documents.py origin/etalon` — «Документы задач заполнены; AGENTS.md и CLAUDE.md совпадают» | |
| Карточки бэклога (28.09) | — | В `docs/KANONICHESKIY_BACKLOG.md`: «## WMS-535» и «## WMS-560» присутствуют (плюс «## WMS-536», постановка, попутно принесена веткой 535) |
| PR в `etalon` создан (`#281`) | — | При первой проверке `mergeable: CONFLICTING` — за время работы `origin/etalon` ушёл вперёд (`a26bc913` → `bbb44bca`, PR #280, WMS-550/555/556/559). Обнаружено `git fetch origin` после создания PR |
| Влит свежий `origin/etalon` (`bbb44bca`) | `11c889a08a159f1b1bc0f72d794bfa4b3ab82998` | Один конфликт: `docs/KANONICHESKIY_BACKLOG.md` — etalon принёс новую карточку «## WMS-559» (дополнительные ШК в сортировке ArtMaks), добавлена к существующим без потерь. Продуктовый код (`sorting_scan_service.py`, `test_wms550_sorting_scan.py`, `requirements/WMS-555.md`, `requirements/WMS-559.md`) слился автоматически без конфликта — ни один файл не пересекался с задачами пакета |
| Повторные проверки после влития свежего etalon | `ruff check .` — все проверки пройдены. `alembic heads` — одна голова `20260927_0561`. `pytest -n auto` (WMS-550 + все тесты 535/560) — 43 passed, 1 skipped (PostgreSQL). `npx tsc --noEmit` и `npm run build` — чисто. `check_task_documents.py origin/etalon` — документы заполнены. Сверка по обновлённому списку из 120 прод-файлов дня — различий, кроме чистых добавок PSP-2, нет | |
| CI на PR #281 — первый прогон | `backlog` FAIL, `backend` FAIL, `frontend-build` PASS | `backlog` (`scripts/ci/check-backlog-ref.sh`): в диапазоне `origin/etalon...HEAD` встретился «WMS-490» (в самом первом коммите ветки, списком задач пакета), а карточки «## WMS-490» в бэклоге не было — WMS-490 в этот выпуск не входит (ждёт WMS-530/531), но гейт требует карточку на любое упоминание номера. `backend` (mypy): те же 13 преэкзистентных ошибок в `scripts/wms555_reset_artmaks.py` (без аннотаций типов — вне объёма «только форматирование») и `scripts/artmaks_cell_qr_mapping.py` (не менялся). Проверено: у уже влитого в `etalon` PR #280 (WMS-550/555/556/559) проверка `backend` тоже FAIL по той же причине — это существующее красное состояние `etalon`, не регрессия этого PR |
| Добавлена карточка «## WMS-490» | — | Честная запись: статус «НЕ В ЭТОМ ВЫПУСКЕ · ЖДЁТ WMS-530/531», без требований/приёмки (они не в этой ветке). Локально `bash scripts/ci/check-backlog-ref.sh origin/etalon` — «Гейт бэклога пройден» |
| CI на PR #281 — второй прогон | `backlog` FAIL (снова) | Коммит с карточкой WMS-490 сам текстом «ждёт WMS-530/531» ввёл новую ссылку на номер без карточки — гейт упал повторно, уже на WMS-530. Добавлена такая же честная заглушка для WMS-530 (статус «НЕ В ЭТОМ ВЫПУСКЕ · РЕАЛИЗОВАНО, ПРИЁМКИ НЕ БЫЛО»). Перед пушем гейт прогнан локально: `bash scripts/ci/check-backlog-ref.sh origin/etalon` — «Гейт бэклога пройден» (список 15 номеров, включая WMS-530) |
| CI на PR #281 — итог (SHA `011683ac`) | `backlog` PASS · `frontend-build` PASS · `backend` FAIL | `mergeable: MERGEABLE`. `backend` красный по mypy — те же 13 преэкзистентных ошибок в двух не относящихся к PSP-2 разовых скриптах; тот же check красный и у уже влитого в `etalon` PR #280 — это существующее состояние проекта, а не регрессия этого PR, и вне объёма поручения «только ruff». PR не сливается — ждёт отдельной команды владельца |
| `git fetch origin` перед mypy-фиксом | — | `origin/etalon` ушёл вперёд ещё раз (`bbb44bca` → `ec99a5d3`, PR #282, WMS-562: перенос заказов упаковки между поставками WB) |
| Влит свежий `origin/etalon` (`ec99a5d3`) | `70486eece5715889a87d3cecf363214203ad732e` | Один конфликт: `docs/KANONICHESKIY_BACKLOG.md` — новая карточка «## WMS-562» из etalon добавлена к существующим. Продуктовый код не пересекался. Гейт бэклога и сверка по прод-файлам дня — без замечаний |
| Mypy-фикс двух скриптов ArtMaks (по требованию владельца — CI PR #281 падал на этом) | `248a790d67fa71344b67938668af2fdfc46465df` | `scripts/wms555_reset_artmaks.py` (11 ошибок) и `scripts/artmaks_cell_qr_mapping.py` (2 ошибки) — только аннотации типов (`main() -> None`, `rows(sql: str) -> list[dict[str, Any]]`, `run(...) -> dict[str, Any]`, `audit: list[dict[str, Any]]`), логика не менялась — сверено diff'ом (только сигнатуры и одно объявление типа). `mypy .` — «Success: no issues found in 515 source files». `ruff check .` — все проверки пройдены |
| `git fetch origin` перед следующим прогоном | — | `origin/etalon` снова ушёл вперёд (`ec99a5d3` → PR #282 уже был влит ранее в этом же разделе; на этот раз новых коммитов не было — влитие не потребовалось) |
| Первый полный `pytest -n auto tests/` на этой ветке | 10 failed, 3358 passed | Впервые прогнан весь набор (раньше — только целевые файлы по задаче). Каждое падение проверено на чистом `origin/etalon` во временном `git worktree`: `test_fbs_openapi_contract`, `test_marketplace_unload_address_storage`, `test_inbound_box_reconciliation`, `test_pick_option_container_sources` — падают уже там, преэкзистентные, не трогал. Оставшиеся два — настоящие регрессии от совмещения задач пакета |
| Фикс двух регрессий | `bbfa0f5ba6b22cbecfd21477598afbed3282aa65` | `test_seller_requisites_autofill.py::test_c7_*` (5 параметризаций) — ответ сохранения ключа WB пополнился полями WMS-535 (`sizes_missing_chrt_id`, `duplicate_chrt_id`, `barcode_conflicts`, `barcode_conflict_details`), добавлены в ожидаемый словарь. `test_wms538_ff_catalog_batch.py` — после WMS-535 основной ШК каталога берётся из `Product.wb_barcode`, а не из сырого `raw_json` карточки (тот же путь, что у настоящего импорта, `wildberries_product_import_service.py:213`); тест заводил товар без этого поля — добавлено. Дополнительно воспроизвёл флаки полного параллельного прогона (`-n auto`): и на этой ветке, и на чистом `origin/etalon` от запуска к запуску падают РАЗНЫЕ тесты (`test_full_flow_pvz_emulator`, `test_wms417_stock_http_contract`) — существующее свойство сьюта под `-n auto`, не регрессия PSP-2 |
| Повторные проверки | `ruff check .` и `mypy .` — чисто. `bash scripts/ci/check-backlog-ref.sh origin/etalon` — «Гейт бэклога пройден» (16 номеров) | |
