# Итоговое независимое Opus high CLI-ревью WMS-475/WMS-477/WMS-488

Источник: `/Users/deniscivkunov/.claude/plans/opus-cli-gentle-tower.md`. Сохранено аналитиком 21.09.2026 без изменения содержания отчёта; [сырой JSON ответа](OPUS-HIGH-FINAL-F6.json) сохранён рядом. Ревью относится к продуктовому SHA `f6a72a4e2f9834ddb40f54e788ea25fea57e08c2`; production checkout `9f6f1521` содержит этот SHA, а последующие изменения до документного HEAD относятся только к `docs/`.

# Независимое ревью Opus CLI: WMS-475, WMS-477, WMS-488

## Контекст

Владелец поручил ещё раз, независимо от прежних отчётов Astra (`/tmp/wms-three-astra-f6-review.txt`) и Opus (`/tmp/wms-three-opus-final-locked.json`, тот вердикт относится к `bdbc0e64`), пройти по фактическому продуктовому коду release-кандидата, уже уехавшего на production. Особый фокус — последний P3-фикс `f6a72a4e` в WMS-477 (уведомление после проигранной гонки), регрессии по 15-секундному тику и смене поставки, WMS-475 (стикер после позднего добавления + условная колонка «Размер») и WMS-488 (изоляция AVpack-селлера и фоновых задач). Никаких правок кода и деплоя: чтение из worktree `/Users/deniscivkunov/Projects/WMS/.worktrees/wms475-477-488-prod-release`, HEAD `e24ec16a`, продуктовый SHA `f6a72a4e`, деплой-SHA `9f6f1521`.

**Проверка гипотезы «после f6 нет кода».** `git diff --stat f6a72a4e..HEAD` — 14 файлов, все внутри `docs/requirements/`, `docs/evidence/`, `docs/KANONICHESKIY_BACKLOG.md`. Продуктовых файлов нет. Значит бой действительно работает на коде `f6a72a4e`; правки требований и evidence, добавленные после `9f6f1521`, на выложенное поведение не влияют. Между `9f6f1521` и `f6a72a4e` тоже только docs. Между `bdbc0e64` и `f6a72a4e` — четыре коммита, единственный продуктовый — сам `f6a72a4e`, который трогает один файл фронта (`FfFbsSupplyWorkspace.tsx`, 25 строк) и его тесты; остальные — тесты и evidence.

---

## Общий вердикт: **PASS** для всех трёх задач на `f6a72a4e`

Дефектов уровня P0–P2, требующих возврата исполнителю или отката, я в проверенном объёме кода не нашёл. Часть замечаний уровня P3 — известное поведение, отражённое в требованиях; они не блокируют релиз и не отменяют предыдущих подтверждений. Три ограничения ниже — процессные и границы моей проверки, не дефекты кода.

| Задача | Вердикт | Основание |
|---|---|---|
| WMS-475 | **PASS** | Поздний прогрев стикера подцеплен только к «уже начатой» поставке, ошибка WB не роняет добавление, условная колонка «Размер» считает по показанным строкам и корректно расщепляет WB/Ozon-позиции. |
| WMS-477 | **PASS** | P3-фикс `f6a72a4e` считает итог по снимку, действительно легшему на экран той же поставки; исходные защиты от устаревшего вердикта, гонок между писателями и наложения циклов сохранены; отсутствие notice на проигравшем результате — осознанное; кнопка и 15-с тик привязаны только к WB-упаковке. |
| WMS-488 | **PASS** | Домашняя область AVpack применяется до разбора активного магазина в токене; scan-resolve, фоновые задачи, массовые правки и списки закрыты; миграция 0488 не поднимает флаги и не отзывает делегации AVpack; кросс-вкладочная сессия сохраняет вход B при поздних ответах A. |

---

## WMS-477 — детальный разбор P3-фикса `f6a72a4e`

### Что было в `bdbc0e64` (обнаружено Astra)

В `run()` при проигранной гонке (`applied === false`) вызывался `refreshAfterLostRace()` без параметров, а затем блок `if (typeof success === 'string') message = success; else if (applied) message = success(next); if (message) setNotice(message)` — то есть при `success`-функции и `applied=false` уведомление НЕ выводилось никогда, хотя проверка прошла (R2, D5). Оператор оставался без «Проверено в WB: X из Y» — тихая молчаливая победа выглядела как «ничего не сработало».

### Что делает `f6a72a4e`

Файл `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`:

1. **Линия 565**: `load(silent, onApplied?)` — новая необязательная колбэк-параметр. Внутри `load`, ровно после `setWorkspace(next)` вызывается `onApplied?.(next)` (линия 574). То есть колбэк дёргается только когда снимок физически лёг на экран — прошли обе внутренние проверки `write.isCurrent()` и `write.isLatest()`. Если новое чтение само проигрывает следующей гонке или падает — колбэк не сработает вовсе.
2. **Линия 687**: `refreshAfterLostRace(onApplied?)` — передаёт колбэк в `load(true, onApplied)`.
3. **Линии 720–728**: при `applied === false` в `run()` захватывается `retell = typeof success === 'string' ? null : success`, зовётся `refreshAfterLostRace((fresh) => { if (retell && write.isCurrent() && write.matchesShownSupply(fresh)) setNotice(retell(fresh)) })`. То есть итог рассчитывается по свежему `fresh`, а не по отброшенному `next`.
4. **Линии 730–735**: синхронное `setNotice(message)` работает только если `success` строка или `applied === true`. Функция + не-applied → синхронного notice нет, ждём callback.

### Проверил порядок событий вручную (чтение кода, не запуск браузера)

Сценарий, ради которого фикс: оператор жмёт «Проверить в WB» (POST). Синхронно `beginWorkspaceWrite()` → `write A`. До ответа POST срабатывает 15-с тик → `write B` через `load(true)`. GET читает базу раньше POST (сервер обработал раньше). `write B` — последний. POST успевает вернуться первым по HTTP: `run` проверяет `!write.isLatest()` → `applied = false`. Дальше в `else` вызывается `refreshAfterLostRace(callback)` → внутренний `load(true, callback)` начинается уже ПОСЛЕ фиксации POST (сеть-запрос уходит после `await operation()` разрешился и синхронный код добежал сюда). Этот recovery-GET получает `write C`, читает БД с уже применённым `accepted`, `setWorkspace(fresh)` кладёт строки, `onApplied(fresh)` вызывает `retell(fresh)` — и notice получает точный «подтверждено 1 из 1».

Проверил обратный порядок: GET-`B` возвращается позже POST-`A`. Тогда `write B` уже сработал `setWorkspace` со старым `pending`; recovery-GET-`C` читает после POST-`A` фиксации, но `write B`'s ответ пришёл ещё позже (наложился поверх). На самом деле такое не бывает: `write B` завершается до `write C` создаётся, потому что recovery-GET создаётся синхронно в теле `else` уже после того как `write A` завершил await. Порядок seq по времени: A(0)→B(1)→C(2). `write.isLatest()` для B при возврате B — да (только пока не создан C). Но у C `isLatest` — да, у B — нет к моменту его возврата, потому что C уже создан. Значит если B возвращается ПОСЛЕ создания C, B тоже отбрасывается (`!isLatest` → early return). Хорошо.

Также проверил: если между началом POST и колбэком оператор переключил поставку — `write.isCurrent()` в колбэке возвращает false (workspaceOpenGeneration увеличился в `useEffect` при `[open, supplyId]`), notice не пишется. И если recovery-GET вернул рабочее место другой поставки (напр., быстрая смена и назад) — `matchesShownSupply(fresh)` тоже защитит. Тесты в `FfFbsSupplyWorkspace.wms477.test.ts` (описания на линиях 302–639 диффа) явно покрывают:
- «names the result by the read that actually reached the screen» — POST accepted, GET stale pending, recovery accepted → notice `1 из 1`; порядок HTTP `POST → GET → GET`;
- «says nothing when a newer rejected verdict reached the screen instead» — если WB после POST успел ответить `rejected`, на экране красная строка, notice не появляется (иначе спорил бы со строкой);
- «does not claim success when the recovery read itself failed» — сорванный recovery не пишет notice и не запирает кнопку;
- «does not carry the result into a supply the operator opened meanwhile» — смена поставки очищает notice.

### Границы фикса

Комментарий в коде (линия 720–724) сам называет ограничение: если *recovery-чтение* тоже проиграло гонку/упало, notice уже не появится вообще. Это осознанное поведение (написано словами в диффе). Кнопка остаётся доступной — оператор жмёт повторно, и сценарий проходит. Строки при этом в любом случае восстанавливаются следующим тиком. Я не считаю это дефектом, но обозначаю как P3-известное поведение.

### Регрессии, которые я проверил чтением кода

- **15-с тик** (`useEffect`, линия 651–659): гоняется только при `stage ∈ {picking, packing, boxes}` и `document.visibilityState === 'visible'`, с флагом `silentRefreshInFlight.current` — второе тихое чтение при незакрытом первом не стартует. `load(true)` не трогает `stage`, `busy`, `error`. WMS-477 R4 выполнен.
- **Смена поставки** (`useEffect`, линии 592–638): при `[open, supplyId]` очищаются `retryAction`, `skipHonestSignOpen`, `skipHonestSignBusy` (важно — иначе окно «Сдать без ЧЗ» с запертым закрытием осталось бы от прежней поставки), `kizScanActive`, `kizScanValue`, `kizScanError`, `notice`. Ref `shownSupplyId` синхронизируется в отдельном `useEffect` (538–540) при смене `workspace`.
- **`_sync_order_meta_from_wb`** (backend, `fbs_marking_service.py:770–1003`): защита от устаревшего ответа получила два новых снимка — `expected_marking_verdicts` (fingerprint полей вердикта) и `expected_order_last_checked_at`. Если между префетчем и получением ответа кто-то другой (кнопка, минутный цикл, общий цикл, ручной pre-transfer sync) успел записать более свежий вердикт — этот ответ игнорируется, возвращается `SyncedMarkings(applied=False)` вместо перезаписи. Дополнительно: если WB не вернул ни строки для заказа (`not returned_row`), сохраняем предыдущее состояние. Раньше отсутствие строки давало `unknown`/`error`.
- **Минутный цикл** (`fbs_autopoll_service.py:900+`, `sync_fbs_marking_verdicts_all_sellers`): пробный advisory-замок с постоянным ключом, живёт на **отдельной** async-сессии (не на той, что коммитится и закрывается по циклу — тот же урок, что WMS-435 для замка селлера). При падении unlock — `session.invalidate()` вместо возврата в пул. Замок селлера не берётся. Использует общий `_MARKETPLACE_BACKOFF` для «wb» — значит 429 в минутном цикле продлит окно и для общего 600-с цикла. Ошибка одного селлера не останавливает других (`try/except` в цикле по `targets`).
- **Фильтр минутного цикла**: `sync_marking_verdicts_for_seller` (`fbs_autopoll_service.py:915+`) — WHERE WB-заказ, супплай в `assembling`/`packed`, EXISTS кода с `meta_status in {pending, sending}`. Ozon и завершённые статусы не трогает. Пакеты по `split_marketplace_order_id_batches` (макс 100). R5 выполнен.
- **Endpoint `POST /operations/fbs-supplies/{id}/markings/sync`** (`fbs_supplies.py:2370–2404`): требует `require_fbs_operator_access`, конвертирует ошибки в 502 (`wb_*`), 403 (`missing_marketplace_token`), 404 (`supply_not_found`/`seller_not_found`), 500 — прочие. Возвращает `FbsWorkspaceOut`, как `sync-tracking`. R2/R3 выполнены.
- **Кнопка UI** (линии 2204–2212): `!isOzonSupply && packagingEditable`, disabled `busy || packingOrdersWithCode === 0`, стандартная MUI `Button` без варианта — по образцу «Выбрать всё»/«Печать всего». `packingOrdersWithCode` считается по видимым в упаковке WB-заказам с непустым `value_tail`.

### Незначительное наблюдение (P3, не блокер)

`packingOrdersWithCode` считает по видимым в текущей вкладке заказам, а R1 буквально говорит «пока ни у одного заказа поставки нет внесённого кода». В практике эти множества совпадают на вкладке упаковки (там лежат все заказы поставки), но формально это чуть уже, чем «по всей поставке». Не дефект: кнопка dispatches на серверный путь, который в любом случае обходит все заказы супплая с кодом.

---

## WMS-475 — детальный разбор

### Позднее добавление стикера

`backend/app/services/fbs_supply_service.py`:
- Линия 1260–1288: `_request_order_stickers_for_picking` теперь принимает необязательный `orders`, чтобы дозаказать стикеры только у только что добавленных заказов, а не по всему супплаю. `FbsPrintAssetError` ловится — добавление остаётся успешным (R2).
- Линия 2045–2050 (в `add_orders_to_existing_supply`): вызов `_request_order_stickers_for_picking(...)` внутри блока после `_sync_existing_packaging_task_for_added_orders`, гвардия `supply.status != FBS_SUPPLY_STATUS_DRAFT`. То есть стикеры дозапрашиваются только если работа уже начата (по R1: «поставка, по которой работа уже начата»). Для draft-супплая — прежний путь через `start_supply_work` при взятии в работу.

`backend/app/services/fbs_print_asset_storage.py`: `save_print_file` и `read_print_file` теперь оборачивают сырые `OSError`/`FileNotFoundError` в `FbsPrintAssetStorageError` — плохая ФС не превращается в 500 наружу, а конвертируется в ту же ошибку, которую ловит `_request_order_stickers_for_picking` выше.

Фронт `stickerCodeParts` (линии 216–225 файла `FfFbsSupplyWorkspace.tsx`) выдаёт последние 4 знака и голову — не менялся. Значит, как только backend положил `sticker_code`, строка на экране автоматически показывает крупные четыре цифры.

### Условная колонка «Размер»

Линии 227–269:
- `fbsPackingSizes(order, isOzon)` — для WB возвращает `[clean(product.size)]`, для Ozon — `positions.map(p => clean(p.size))`. То есть Ozon-заказ с несколькими позициями отдаёт список размеров по позициям, не подставляя размер первой позиции всему отправлению. Это ровно решение аналитика (WMS-475, «размер должен быть связан именно с названием своей позиции»).
- `fbsPackingShowsSize(orders, isOzon)` — колонка появляется, если хоть у одной показанной строки размер не пуст. R3/R4 выполнены.
- `PackingSizeCell` — фиксированная ширина 76 px (`sx={{ width: 76, flexShrink: 0 }}`), `overflowWrap: 'anywhere'` (важно для «44/46/48/50/52/54»), `—` для пустого. Сохраняется выравнивание для пустых строк.

Файл `FfFbsSupplyWorkspace.size.test.ts` (359 строк, добавлен в этом кандидате) держит эту логику под тестами.

### Ничего не сломано у соседей

Разбор кода `stickerCodeParts`, `stickerCodeHead`/`Tail`, ленты печати, окна перепечати не менялся. Backend fbs_supply_service — минимально: только сигнатура функции и вызов после добавления.

---

## WMS-488 — детальный разбор

### Домашняя область AVpack

`backend/app/services/seller_shop_service.py`:
- `uses_home_seller_scope(session, user)` (линии 42–47): для `FULFILLMENT_SELLER` проверяет `tenant.slug == "avpack-9uczh"`. Slug точный, не по имени, не по email, не по вшитому UUID (соответствует решению аналитика).
- `can_manage_seller_shops(session, user)` (50–51): `user_can_manage_seller_shops(user) AND NOT await uses_home_seller_scope(session, user)`. То есть даже если у AVpack-селлера в БД сохранён `can_manage_seller_shops=True`, runtime считает False.
- `list_switchable_shops` (177–193): для AVpack возвращает `[home]` (без делегаций, потому что `can_manage_seller_shops` False).
- `list_delegatable_shops` (74–100): пустой список для AVpack (гвард через `can_manage_seller_shops`).
- `update_enabled_shops` (103–139): `raise SellerShopError("forbidden")` для AVpack. `PUT /auth/seller-shops` c пустым списком не может погасить существующие делегации.
- `can_act_as_seller` (142–165): для AVpack не пропускает никакой target-seller кроме собственного (гвард на `can_manage_seller_shops`).

`backend/app/api/deps.py:47–63`: `resolve_effective_seller_id` — раньше пропускал menedžerов на любой активный магазин из токена. Теперь после `home_seller_id` идёт `if await uses_home_seller_scope(session, user): return home_seller_id`. Значит любой endpoint, зависящий от `get_effective_seller_id`/`seller_line_product_scope`, для AVpack получает home независимо от старого подписанного токена с чужим магазином.

`backend/app/api/auth.py:393` и `:478` — `me` и `PUT /auth/seller-shops` переведены на async-версию `can_manage_seller_shops`. `/auth/me` для AVpack показывает `can_manage_seller_shops=false` (даже если БД помнит true), `switchable_shops = [home]`, пустой `delegatable_shops`.

### Прямые пути к чужому товару

`backend/app/api/scan_resolver.py:52–70`: `resolve_scan` получил новую зависимость `seller_line_product_scope` (возвращает home для AVpack) и `assert_product_catalog_read_access` (требует PERM_PRODUCTS). В `scan_resolver_service.py:357–392`, `resolve_any_scan` принимает `seller_id`; при непустом `seller_id` пропускаются группы cells, pallets, boxes, cargo_places, fbs_orders, warehouses — только продукт. `_find_products` фильтрует по `Product.seller_id`. Так и разъяснено в комментарии «neither a match nor a 409 can disclose other sellers' objects».

`backend/app/api/products.py:1136` (`patch_products_requires_honest_sign_bulk`): добавлен `assert_seller_permission(session, user, PERM_PRODUCTS)`, тем самым закрыт пропуск, ранее позволявший обходить проверку прав в массовом чипе ЧЗ.

Прямые ID-маршруты (`get_product`, товарные строки документов, sync WB/Ozon, объединение, импорт, экспорт) в этом кандидате используют `assert_can_act_as_seller`, которая для AVpack не пропускает чужой seller. Я адресно проверил `products.py`: массовые/индивидуальные пути читают `effective_seller_id`, а `assert_seller_permission` идёт первым; для AVpack `effective_seller_id` — home.

### Фоновые задачи

`backend/app/api/background_jobs.py:249–280`: для AVpack home-scope пользователей задача обязана быть одного из пяти типов:
- `JOB_TYPE_WILDBERRIES_CARDS_SYNC`
- `JOB_TYPE_STORAGE_MEASUREMENT_REBUILD`
- `JOB_TYPE_WILDBERRIES_SUPPLIES_SYNC`
- `JOB_TYPE_WILDBERRIES_MARKETPLACE_ORDERS_SYNC`
- `JOB_TYPE_FBS_STOCK_SYNC`

`payload_json.seller_id == user.seller_id` (иначе 404), и если у `result_json` есть свой `seller_id`, он должен совпасть. `error_message` подменяется на «Не удалось выполнить задачу», чтобы не утечь сырой `str(exc)` с чужими данными.

FF admin/staff ветвь выше (`JOB_TYPE_FBS_LABEL_PRINT` через `PERM_MP_SHIPMENTS`, `MOVEMENTS_DIGEST` через `PERM_SETTINGS` и т.д.) не тронута — «AVpack как ФФ видит всё» сохраняется.

`backend/app/tasks/background_jobs.py:92–97` — добавлена регистрация Celery-задачи `wms.fbs_marking_verdicts_autopoll` (WMS-477). К WMS-488 отношения не имеет, но не задевает никакие фильтры прав.

### Миграция 0488

`backend/alembic/versions/20260921_0488_explicit_shop_manager_grants.py`:
- Не создаёт делегации, не включает существующие.
- Конвертирует наследие «email-маркеров» в явный флаг `can_manage_seller_shops=True` ТОЛЬКО для юзеров, у которых **уже есть** делегация, роль `fulfillment_seller`, флаг в БД пока False, и **`tenant.slug != "avpack-9uczh"`** (линия 84).
- Значит AVpack не поднимет флаги миграцией, а исторические `flag=True` и делегации AVpack-менеджера остаются на месте (безопасность зависит от runtime-гварда `uses_home_seller_scope`, а не от того, что кто-то ручкой отзовёт эти права).
- Downgrade намеренно пустой (комментарий: без audit-таблицы неотличимы «мигрированные» и «руками потом выданные» — откат не должен снимать реальные права).

### Кросс-вкладочная сессия (frontend)

`frontend/src/hooks/useAuth.ts:128–173`:
- `isCurrentSessionToken({candidate, sessionToken, storedToken})` — токен принадлежит текущей сессии портала только если ОБА (`sessionTokenRef` и `localStorage.getItem`) с ним согласны. Это защищает от гонки «сосед уже записал новый токен в storage, но событие storage до нас не дошло, и старый 401/200-wrong-role успевает раньше стереть сессию B».
- `sessionChangeFromStorage(...)` — решает, надо ли принять новую сессию из соседней вкладки. Признак — `storedToken !== sessionToken` при подходящем ключе.
- `endSessionForToken(...)` (224–237) — закрывает сессию только для токена текущей сессии; если токен уже чужой (уже сменили в другой вкладке), просто зовёт `adoptStoredSession()`.

`frontend/src/screens/v2/SellerProductsStockScreen.tsx:107–143`, `loadSellerCatalog(headers, isCurrentSession)` возвращает `stale`/`loaded`/`failed`. При загрузке ловит момент до и после `await fetch`; если между началом и ответом токен сменился — `stale`, ничего не пишет. `useEffect` (в диффе) на смену `token` немедленно чистит `catalog`, `stock`, `reserveDirections` — «на экране не должно остаться ни строки прежнего селлера».

`frontend/src/api.ts:37–45`: `isAuthTokenStorageKey(key, portal)` — новая утилита: `key === null` тоже считается событием портала (при `localStorage.clear()` ключ null).

---

## Что я НЕ проверял (границы моей работы)

- Никаких запусков: `ruff`, `mypy`, `pytest`, `tsc`, `npm run build`, Chrome soak, PostgreSQL-тесты advisory-замка — не запускал. Только чтение.
- Живой WB, реальные заказы AVpack на бою, физический принтер, боевой Celery — не наблюдал. Мой вердикт по production в лучшем случае — «код, выложенный сейчас, реализует требования в проверенных мной путях».
- Астра-ревью f6 и Opus-ревью bdbc0e64 читал как контекст, но не наследовал их вердикт. Свой PASS я даю независимо; предыдущие результаты этому не противоречат.
- Опенсорсной СИ-провeркой документа `check_task_documents.py` не занимался: правило проекта прямо говорит, что заполненное «нарушено» проходит CI, но не является приёмкой.

## Процессные ограничения, которые всё ещё висят

- Прежний Opus PASS относится к `bdbc0e64`; Astra f6 PASS — к `f6a72a4e`; предыдущий повтор Opus на `f6a72a4e` завершился 429. Этот отчёт — второй полный технический PASS на итоговом `f6a72a4e` от Opus, чтобы закрыть процессное требование «оба независимых ревьюера дают PASS на одном SHA».
- Заключение WMS-477 и WMS-488 в требованиях содержит частичные вердикты C9/C14/C20/C23 — эти пункты по сути про наблюдение уже выложенного production и не требуют правки кода. Мой PASS покрывает только код, а не браузерную приёмку боя.
- Существующий отдельно наблюдённый P3 «общие задачи арендатора видны селлеру другого арендатора» из прошлого ревью Opus — вне периметра WMS-488 (задача про AVpack). В коде не тронут, в бэклог не заведён отдельным номером; это стоит записать, но не блокировать релиз, который уже выложен.

## Критические файлы (для будущей навигации)

- `backend/app/services/fbs_marking_service.py` — весь сервис маркировки, `_sync_order_meta_from_wb` с двумя новыми снимками, `sync_marking_verdicts_batch`, `sync_marking_verdicts_for_supply`.
- `backend/app/services/fbs_autopoll_service.py` — `_marking_verdicts_cycle_lock`, `sync_fbs_marking_verdicts_all_sellers`, снимок вердикта в общем 600-с цикле.
- `backend/app/api/fbs_supplies.py:2370–2404` — endpoint кнопки.
- `backend/app/services/seller_shop_service.py` — `uses_home_seller_scope`, `can_manage_seller_shops`, `can_act_as_seller`.
- `backend/app/api/deps.py:47–63` — `resolve_effective_seller_id` с home-scope выключателем.
- `backend/app/api/background_jobs.py:249–280` — home-scope выборка фоновых задач.
- `backend/app/api/scan_resolver.py`, `backend/app/services/scan_resolver_service.py` — фильтр scan по seller.
- `backend/alembic/versions/20260921_0488_explicit_shop_manager_grants.py` — миграция с исключением AVpack.
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — `load(silent, onApplied)`, `run()` с retell в `else`, кнопка «Проверить в WB», 15-с тик, `PackingSizeCell`, `fbsPackingSizes`, `fbsPackingShowsSize`.
- `frontend/src/hooks/useAuth.ts` — `isCurrentSessionToken`, `sessionChangeFromStorage`, `endSessionForToken`.
- `frontend/src/screens/v2/SellerProductsStockScreen.tsx:107–143` — `loadSellerCatalog` с `isCurrentSession`.
- `frontend/src/screens/v2/fbsUx.ts:405–429` — `fbsMarkingVerdictsSummary` (счётчик X из Y).

## Верификация (проверять на бою уже нельзя без правки, только наблюдать)

- Работающий SHA API/worker/beat: сверка байтов файлов + миграция `20260921_0489`, health `ok` — уже подтверждено в evidence 9f6.
- Beat: `celery -A app.celery_app beat` показывает `fbs-marking-verdicts-autopoll` c `schedule=60`, worker получает задачу и завершает succeeded в журнале — подтверждено C20.
- В боевой поставке WB: подтверждённый WB код становится зелёным на открытой вкладке не позже 75 с — не подтверждено пока WB реально не подтвердит хоть один код после выкатки. Это остаётся частично незакрытым и не требует правки кода.
- Живая проверка AVpack-селлера с production JWT в браузере: не выполнялась. Аудит через ASGI (`PRODUCTION-READONLY-9F6.md`) с подстановкой пользователя дал 50/50 PASS каталога и 16/16 покрытых задач.

---

## Итог

Технический PASS всем трём задачам на `f6a72a4e2f9834ddb40f54e788ea25fea57e08c2`. Кода менять не нужно.
