# Screenshot manifest

## Provenance

- Interaction executor: system-review orchestrator, реальный in-app Browser, клики по левому меню staging.
- Scenario design: product reviewer, `01_BROWSER_EXECUTION_CHECKLIST_RU.md`.
- Visual adjudicator: product reviewer; каждый файл ниже лично открыт через `view_image` с `detail=original`.
- Evidence root: `/Users/deniscivkunov/Projects/WMS/.worktrees/system-review-orchestrator-20260812/docs/reviews/system-wide/runs/2026-08-12/orchestrator/evidence/`.
- Role: synthetic FF admin.
- Первый batch: CSS viewport 1280×720, fullPage. У FBS фактическая PNG-height 733 из-за fullPage; остальные проверенные размеры 1280×720.
- Stable desktop batch: CSS viewport 1920×1080, `window.devicePixelRatio=1`; эти значения оркестратор прочитал в той же активной browser override, PNG также имеет 1920×1080 pixels. Поэтому stable-файлы засчитываются как настоящий desktop viewport. Transitional captures с тёмными gutter'ами используются только как доказательство клика/состояния и не участвуют в layout verdict.

## Batch 1 — destinations after real menu click

| Файл | Лично просмотрен | Product verdict | Что доказано | Что не доказано |
| --- | --- | --- | --- | --- |
| `UI-FF-MP-SHIPMENTS__synthetic-admin__1280x720__clicked.png` | да | `RETEST_VIEWPORT` | пункт меню открыл MP screen; заголовок, new-document seller control и filters присутствуют | правая часть/таблица/actions из-за крупного effective scale; action/result/reload/failure |
| `UI-FF-FBS__synthetic-admin__1280x720__clicked.png` | да | `PASS_EMPTY` | FBS route, 5 status tabs, seller/search, 4 эталонные columns, empty state, refresh/pull actions | populated list, selection, supply workspace, reload/failure |
| `UI-FF-RECEPTION__synthetic-admin__1280x720__clicked.png` | да | `PASS_EMPTY + RETEST_VIEWPORT` | очередь пуста и сообщает это | полное описание и document actions; normal/reload/failure |
| `UI-FF-SORTING__synthetic-admin__1280x720__clicked.png` | да | `PASS_EMPTY + RETEST_VIEWPORT` | пустая очередь и пояснение sorting buffer | полный текст/normal/putaway/reload/failure |
| `UI-FF-PACKAGING__synthetic-admin__1280x720__clicked.png` | да | `RETEST_VIEWPORT` | empty task table, pending-marking и create-task actions существуют | layout: контент сжат в узкую полосу, справа тёмный gutter; все actions/states |
| `UI-FF-CELLS__synthetic-admin__1280x720__clicked.png` | да | `EMPTY_DEAD_END_CANDIDATE + RETEST_VIEWPORT` | warehouse list пуст и просит создать первый | create action может быть за crop; normal/actions |
| `UI-FF-SELLERS__synthetic-admin__1280x720__clicked.png` | да | `RETEST_VIEWPORT` | seller row `Review Seller` существует | явное действие строки/создание сотрудника из-за crop |
| `UI-FF-CATALOG__synthetic-admin__1280x720__clicked.png` | да | `PASS_EMPTY` | create seller/import/create product/search/filter и понятный empty state | действие controls, populated table, reload/failure |
| `UI-FF-INVENTORY__synthetic-admin__1280x720__clicked.png` | да | `FAIL_PROCESS_GAP` | nav ведёт только на placeholder | весь цикл inventory отсутствует |
| `UI-FF-HONEST-SIGN__synthetic-admin__1280x720__clicked.png` | да | `RETEST_VIEWPORT` | summary cards, upload, ledger, seller/search; нулевой pool state | полный shell/layout и все actions/states |
| `UI-FF-SETTINGS__synthetic-admin__1280x720__clicked.png` | да | `PASS_NORMAL` | два warehouse/print toggles, calculation month, empty staff, add-user form | validation/save/reload/permissions/rate |
| `UI-FF-DASHBOARD__synthetic-admin__1280x720__clicked.png` | да | `FAIL_TERM + RETEST_VIEWPORT` | dashboard/empty inbound/MP section; внутреннее `Статус «submitted»` видно пользователю | row click, полная таблица, reload/failure |

## Quality note по batch 1

Эффективный масштаб screenshots непоследователен:

- FBS, Catalog и Settings выглядят как нормальный 1280-wide desktop;
- MP, Reception, Sorting, Cells, Sellers, Inventory и Dashboard выглядят примерно как 2× zoom и обрезают правую часть;
- Packaging и Honest Sign занимают узкую центральную полосу с тёмными gutter’ами.

Это не объявлено app defect, потому что один batch даёт три разных layouts при одинаковой подписи viewport. Stable desktop batch ниже снят при авторитетно проверенных `window.innerWidth=1920`, `window.innerHeight=1080`, `devicePixelRatio=1` и заменяет transitional-файлы для layout verdict. Контентные факты `inventory placeholder` и `submitted` от capture-state не зависят.

## Недостающий обязательный evidence

- auth before/failure/reload/logout и прямой wildcard;
- FBS populated stages, selection/preflight и обе route variants коробов;
- normal/partial/reload/failure для inbound, sorting и packaging;
- MP lines/plan/pack/boxes/ship/failure;
- seller submit/product sync/ЧЗ actions/notifications;
- FF-staff role и mobile/device screenshots.

Stable 1920×1080 destination batch, seller routes, FBS tabs/Stocks/reload, durable cells и draft workflows уже получены. Все оставшиеся interactive controls перечислены в route/action inventory как `NOT_RUN` либо `BLOCKED_*`.

## Batch 2 — stable destination screens, CSS viewport 1920×1080

Все 12 файлов лично открыты. Оркестратор отдельно доказал в той же Browser override `window.innerWidth=1920`, `window.innerHeight=1080`, `devicePixelRatio=1`; PNG имеет 1920×1080 pixels. Stable-файлы поэтому закрывают требование второго desktop viewport. Отдельные кадры сразу после click/submit с тёмными gutter'ами помечаются transitional и не подменяют stable verdict.

| Файл | Verdict | Независимое продуктовое заключение |
| --- | --- | --- |
| `UI-FF-DASHBOARD__synthetic-admin__1920x1080__stable-2s.png` | `PASS_EMPTY + FAIL_TERM` | Пустой план понятен; `Статус «submitted»` повторно подтверждён. |
| `UI-FF-MP-SHIPMENTS__synthetic-admin__1920x1080__stable-2s.png` | `PASS_EMPTY` | Назначение, seller, create action, filters и `Нет документов` читаются. Details workflow не использован. |
| `UI-FF-FBS__synthetic-admin__1920x1080__stable-2s.png` | `PASS_EMPTY` | Утверждённые tabs/filter/search/table layout видны в desktop viewport. |
| `UI-FF-RECEPTION__synthetic-admin__1920x1080__stable-2s.png` | `PASS_EMPTY` | Понятная очередь; normal/action не доказаны. |
| `UI-FF-SORTING__synthetic-admin__1920x1080__stable-2s.png` | `PASS_EMPTY` | Смысл пустого состояния и sorting buffer виден. |
| `UI-FF-PACKAGING__synthetic-admin__1920x1080__stable-2s.png` | `PASS_EMPTY` | `Нет открытых заданий`; populated task и действия ещё не доказаны. |
| `UI-FF-CELLS__synthetic-admin__1920x1080__stable-2s.png` | `PASS_EMPTY` | Empty text виден; workflow ниже доказывает create action. |
| `UI-FF-SELLERS__synthetic-admin__1920x1080__stable-2s.png` | `PASS_LIST` | Seller row виден; создание/permissions не использованы. |
| `UI-FF-CATALOG__synthetic-admin__1920x1080__stable-2s.png` | `PASS_EMPTY` | Search/filter/table visible; create validation workflow ниже использован. |
| `UI-FF-INVENTORY__synthetic-admin__1920x1080__stable-2s.png` | `FAIL_PROCESS_GAP` | Placeholder повторно подтверждён. |
| `UI-FF-HONEST-SIGN__synthetic-admin__1920x1080__stable-2s.png` | `PASS_EMPTY` | KPI/actions/filters readable; действия не использованы. |
| `UI-FF-SETTINGS__synthetic-admin__1920x1080__stable-2s.png` | `PASS_NORMAL` | Верхние настройки понятны; address-storage mutation намеренно не выполнялась из-за массовой миграции остатков. |

## Batch 2 — warehouse/cell workflow

| Файл | Verdict | Заключение |
| --- | --- | --- |
| `UI-FF-CELLS__warehouse-create__1920x1080__before-submit.png` | `PASS_ACTION_FORM` | Открыта форма создания склада. |
| `UI-FF-CELLS__warehouse-create__1920x1080__result.png` | `PASS_RESULT` | Новый isolated warehouse появляется строкой. |
| `UI-FF-CELLS__cell-create-1__1920x1080__before-submit.png` | `PASS_ACTION_FORM` | Форма связывает ячейку с выбранным warehouse и просит стеллаж/сторону/уровень/место. |
| `UI-FF-CELLS__cell-create-1__1920x1080__result.png` | `PASS_RESULT_BUT_CONTEXT_HIDDEN` | Возврат к warehouse list; ячейки не видны без выбора строки. |
| `UI-FF-CELLS__cell-create-2__1920x1080__result.png` | `PASS_RESULT` | В нормальном масштабе видны warehouse, две реальные ячейки с barcode и virtual `Сортировка`. |
| `UI-FF-CELLS__warehouse-and-cells__1920x1080__reload.png` | `PASS_RELOAD_WAREHOUSE` | Warehouse сохраняется. После reload нужно снова выбрать row; ячейки на этом кадре не видны. |
| `UI-FF-CELLS__warehouse-and-cells__1920x1080__reload-reselect.png` | `FAIL_EVIDENCE_CLAIM` | Несмотря на имя и описание batch, PNG показывает только выбранную строку склада; обе физические ячейки и virtual `Сортировка` не видны. Durable cells gate этим файлом не закрыт. |
| `UI-FF-CELLS__warehouse-and-cells__1920x1080__reload-reselect-visible.png` | `PASS_DURABLE_RELOAD` | Исправленный stable capture после reload и повторного выбора склада показывает обе физические ячейки `REV-A 1.1`, `REV-A 2.2`, их barcodes и virtual `Сортировка`. Durable gate закрыт этим, а не предыдущим файлом. |

Создание выполнено оркестратором внутри isolated synthetic tenant. Delete/print/error не выполнялись; отдельное cleanup/recovery evidence не передано.

## Batch 2 — product create validation

| Файл | Verdict | Заключение |
| --- | --- | --- |
| `UI-FF-CATALOG__product-create__1920x1080__before-submit.png` | `PASS_ACTION_FORM` | Заполнены product fields, обязательный seller фактически пуст. |
| `UI-FF-CATALOG__product-create__1920x1080__result.png` | `PASS_FAILURE_VALIDATION` | Native validation фокусирует seller и показывает `Заполните это поле`; dialog и введённые values остаются. |
| `UI-FF-CATALOG__product-create__1920x1080__reload.png` | `PASS_NO_FALSE_CREATE` | После reload товара нет, как и должно быть после validation failure. |

Static baseline дополнительно показывает `return` во всех non-2xx branches, поэтому предположение о закрытии dialog после API error не подтверждено. Для API duplicate/server failure нужен отдельный fault fixture.

## Batch 3 — seller portal 1280×720

Все пять файлов лично открыты.

| Файл | Verdict | Заключение |
| --- | --- | --- |
| `UI-SELLER-FIRST-LOGIN__seller__1280x720__result.png` | `PASS_AUTH_RESULT + RETEST_VIEWPORT` | Seller portal и 4 sidebar items доступны; Documents screen виден. Правая часть actions cropped. |
| `UI-SELLER-документы__seller-empty__1280x720__loaded.png` | `RETEST_STATE` | Selected nav виден, main pane пуст; это противоречит first-login screenshot того же route и требует stable repeat. |
| `UI-SELLER-товары__seller-empty__1280x720__loaded.png` | `PASS_EMPTY + RETEST_VIEWPORT` | API sync action и FBS onboarding видны; catalog table/controls справа обрезаны. |
| `UI-SELLER-честный-знак__seller-empty__1280x720__loaded.png` | `PASS_EMPTY + RETEST_VIEWPORT` | Нулевые личные/общие остатки, upload и ledger actions видны; часть cards cropped. |
| `UI-SELLER-настройки__seller-empty__1280x720__loaded.png` | `RETEST_VIEWPORT` | Transitional capture с узкими cards и тёмным фоном не пригоден для layout verdict. Секретные формы не открывались. |

Seller credentials применил оркестратор в разрешённом staging контуре; значения в evidence/report не раскрываются. Действия seller screens ещё не использованы, поэтому route visibility не превращается в workflow PASS.

## Batch 4 — stable seller portal и реальные действия, CSS viewport 1920×1080

Каждый файл лично открыт. Runtime interaction выполнил оркестратор; продуктовую оценку вынес product reviewer.

| Файл | Verdict | Заключение |
| --- | --- | --- |
| `UI-SELLER-DOCUMENTS__existing-test-seller__1920x1080__stable-2s.png` | `PASS_LIST` | Документы, filters и три create-actions видны; список содержит MP unload. |
| `UI-SELLER-PRODUCTS__existing-test-seller__1920x1080__stable-2s.png` | `PASS_EMPTY` | Понятны каталог, API sync и FBS-stock explanation; данных товара нет, action не запускался из-за отсутствующего WB key. |
| `UI-SELLER-HONEST-SIGN__existing-test-seller__1920x1080__stable-2s.png` | `PASS_EMPTY` | Нулевые личные/общие pools, upload и ledger actions понятны; секретные/расходные действия не выполнялись. |
| `UI-SELLER-SETTINGS__existing-test-seller__1920x1080__stable-2s.png` | `PASS_STATUS` | Статусы WB и ЧЗ-интеграции видны без открытия credentials forms; WB key явно `не добавлен`, sync disabled. |
| `UI-SELLER-DOCUMENTS__discrepancy-action__1920x1080__clicked.png` | `FAIL_PROMISED_ACTION` | Реальный CTA не создаёт акт: после клика показывает error alert `будет реализован ... на следующем этапе`. PROD-005 runtime confirmed. |
| `UI-SELLER-INBOUND__empty-draft__1920x1080__before-save.png` | `PASS_DRAFT_EDIT` | Draft с датой и planned boxes, без product lines; экран прямо подсказывает добавить товары. |
| `UI-SELLER-INBOUND__empty-draft__1920x1080__result.png` | `PASS_DRAFT_PERSIST` | После сохранения строка `Поставка / Черновик / 0` появляется в Documents. Это не finding: действующий контракт разрешает черновики до добавления строк; submit ещё не доказан. |

## Batch 5 — MP unload draft, CSS viewport 1920×1080

| Файл | Verdict | Заключение |
| --- | --- | --- |
| `UI-FF-MP-SHIPMENTS__create-draft__1920x1080__before-submit.png` | `PASS_BEFORE` | FF admin выбрал isolated seller, create action доступен, список изначально пуст. |
| `UI-FF-MP-SHIPMENTS__create-draft__1920x1080__result.png` | `TRANSITIONAL_EXCLUDED` | Кадр сразу после click имеет тёмные gutter'ы и не используется для layout verdict. |
| `UI-FF-MP-SHIPMENTS__create-draft__1920x1080__stable-4s.png` | `PASS_DRAFT_RESULT` | Создан `Отгрузка №000001`, seller и FF warehouse привязаны; план и распределение 0, обязательная дата и WB warehouse ещё пусты. |
| `UI-FF-MP-SHIPMENTS__create-draft__1920x1080__reload.png` | `PASS_RELOAD` | Draft сохраняется и появляется в таблице как `Черновик`, строк 0. Пустой draft разрешён действующим TC; confirm/ship без строк не проверялись. |
| `UI-FF-MP-SHIPMENTS__draft-detail__1920x1080__opened.png` | `PASS_REOPEN` | Сохранённый draft повторно открыт и остаётся редактируемым. Product add/date/WB warehouse/plan/pack/boxes/failure не выполнены. |

Тот же draft виден seller в `Документы`, что подтверждает cross-portal readback. Это ещё не сквозной MP workflow: строки, упаковка, короба, подтверждение, ship и failure остаются `NOT_RUN`.

## Batch 6 — FBS navigation и WB stocks, CSS viewport 1920×1080

Все семь файлов лично открыты. Внешние WB mutations (`Забрать заказы из WB`, выгрузка остатков, создание/изменение bindings) намеренно не запускались.

| Файл | Verdict | Заключение |
| --- | --- | --- |
| `UI-FF-FBS__orders-новые__1920x1080__stable.png` | `PASS_EMPTY` | `Новые`, seller/search, четыре эталонные columns и понятный empty state видны. |
| `UI-FF-FBS__orders-в-работе__1920x1080__stable.png` | `PASS_EMPTY` | Вкладка реально выбрана; вне `Новые` появляется допустимая колонка `Статус`. |
| `UI-FF-FBS__orders-в-доставке__1920x1080__stable.png` | `PASS_TAB_CLICK + TRANSITIONAL_LAYOUT` | Active tab доказан, но кадр с тёмными gutter'ами не засчитывает table/empty layout. |
| `UI-FF-FBS__orders-завершённые__1920x1080__stable.png` | `PASS_EMPTY` | Active tab, filters, table header и понятный empty state видны. |
| `UI-FF-FBS__orders-отменённые__1920x1080__stable.png` | `PASS_TAB_CLICK + TRANSITIONAL_LAYOUT` | Active tab доказан; table/empty layout не засчитан из-за transitional capture. |
| `UI-FF-FBS__wb-stocks__1920x1080__stable.png` | `PASS_EMPTY` | Реально открыта `Остатки WB`, выбран Review Seller, доступны refresh/add-binding, export disabled без bindings; active bindings отсутствуют. |
| `UI-FF-FBS__reload__1920x1080__result.png` | `PASS_RELOAD_TAB` | Reload сохраняет `Остатки WB`; seller selection сбрасывается, actions disabled до повторного выбора. Это не объявлено defect без требования сохранять filter. |

Итог FBS batch: навигация по всем пяти status groups и Stocks/reload закрыта. Populated order, выбор, supply creation, `Состав → Подбор → Упаковка и маркировка → Короба`, print/retry/failure не пройдены; live-WB actions имеют `BLOCKED_EXTERNAL_MUTATION`.
