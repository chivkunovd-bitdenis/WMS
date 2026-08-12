# Реестр маршрутов и действий

## Как читать реестр

`STATIC` означает, что маршрут и action inventory подтверждены кодом runtime-базы. Это не продуктовый PASS. `VISUAL` означает, что screenshot лично просмотрен. `INTERACTION` появляется только после реального клика/ввода/результата. Каждый неиспользованный элемент остаётся `NOT_RUN`, `N/A_BY_ROLE` или `BLOCKED_*`.

## Публичный вход

| Маршрут | Роль | Что видит и делает пользователь | Состояния | Факт |
| --- | --- | --- | --- | --- |
| `/` | anonymous | Переключает вход/регистрацию, вводит email и пароль, переходит в seller portal, отправляет форму, завершает initial-password setup | initial, validation, bad credentials, busy, portal mismatch, success, logout | STATIC; Browser evidence ожидается |
| `/seller/` без сессии | anonymous seller | Вводит seller email/password; регистрация фактически не отправляется | initial, validation, bad credentials, mismatch, success | success/login result VISUAL; bad credentials/logout `NOT_RUN` |

## FF portal — shell и основные маршруты

| Маршрут | Роль/право | Экран и все явные действия | Физический смысл | Runtime |
| --- | --- | --- | --- | --- |
| `/app/dashboard` | authenticated FF | redirect на `/app/ff/dashboard` | вход в смену | STATIC |
| `/app/ff/dashboard` | FF | nav, notification bell, logout; строки/графики inbound и MP outbound открываются кликом | начальник смены выбирает следующую очередь/документ | VISUAL 1280; action rows `NOT_RUN` |
| `/app/ff/mp-shipments` | `mp_shipments` | создать MP shipment/акт расхождения; seller/sort/filter; открыть document; внутри Products/Packaging, add/delete product, invoice/TZ print, picking scan, boxes create/import/fill/remove/print/copy/delete, submit/cancel/ship и confirmations | собрать и отгрузить FBW/MP документ | WORKFLOW: isolated empty draft create → detail → reload list → reopen; cross-portal seller readback. Остальные actions `NOT_RUN` |
| `/app/ff/supplies-shipments` | FF | redirect в `/app/ff/reception` | legacy alias | STATIC |
| `/app/ff/reception` | `reception` | открыть строку; document full-screen; verify/complete recount, distribute, scan/add barcode, add products, submit/reopen/close, invoice print; box import/create/fill/delete/print; distribution warehouse/location/add/save/complete/reopen/location print; discrepancy confirm | машина/короба → поштучный пересчёт → сортировка | VISUAL PASS_EMPTY 1280+1920; actions `NOT_RUN` |
| `/app/ff/sorting` | `reception` | открыть заявку, выбрать короб/товар, location hint, scan/manual putaway, сохранить частичный факт, завершить, перейти к упаковке | буфер сортировки → физическая ячейка | VISUAL PASS_EMPTY 1280+1920; actions `NOT_RUN` |
| `/app/ff/packaging` | `packaging` | открыть task, pending-marking, создать task; line print, reprint/defect menu, confirm from shelf, pack, complete/cancel; перейти в связанный MP document | упаковать/маркировать подобранный товар | VISUAL PASS_EMPTY 1280+1920; populated actions `NOT_RUN` |
| `/app/ff/packaging/pending-marking` | `packaging` | список ожидающих ЧЗ, открыть task, back/refresh | найти задания, блокируемые маркировкой | STATIC; `NOT_RUN` |
| `/app/ff/products` | admin | search, seller filter, pagination, photo hover, packaging instruction dialog, import preview/apply, refresh | подготовить складской каталог | VISUAL PASS_EMPTY 1280+1920; manual create required-seller validation WORKFLOW; remaining actions `NOT_RUN` |
| `/app/catalog` | `cells` | выбрать склад, создать склад, открыть racks/locations, suggest location, создать location/product, barcode print | организовать физические места хранения | WORKFLOW: warehouse + 2 cells created; reload/reselect shows both cells + virtual sorting. Print/delete/failure `NOT_RUN` |
| `/app/ff/sellers` | admin | список, открыть форму seller, создать seller с brand/email, открыть staff/permissions where available | подключить клиента и его сотрудников | VISUAL PASS_LIST 1280+1920; actions `NOT_RUN` |
| `/app/catalog/products` | admin/legacy | create seller, Excel import, create product, search/filter/sort, photo, TZ, print/save | альтернативный каталог/остатки | STATIC; `NOT_RUN` |
| `/app/ff/inventory` | `inventory` | только заголовок и «Раздел в разработке» | цикл пересчёта отсутствует | VISUAL 1280; confirmed GAP |
| `/app/ff/notifications` | FF | открыть bell/list, mark one/read all, pagination where present | разобрать события смены | STATIC; `NOT_RUN` |
| `/app/ff/settings` | admin/`settings` | address storage toggle, separate ЧЗ/ШК print toggle, calculation month, add staff, permissions/rate | правила склада и персонала | VISUAL 1280+1920; address toggle `BLOCKED_DESTRUCTIVE_SHARED_STOCK`, remaining controls `NOT_RUN` |

## FF portal — FBS

| Маршрут/зона | Действия | Что у оператора в руках | Runtime |
| --- | --- | --- | --- |
| `/app/ff/fbs`, section `Заказы` | tabs Новые/В работе/В доставке/Завершённые/Отменённые; seller filter; search; refresh; забрать из WB; выбрать один/все совместимые orders; открыть create-supply preflight; открыть supply row | новые заказы и пустая тележка; на этом шаге физического товара ещё нет | UI_CLICKED: все 5 tabs; empty states visual. Populated selection/supply `NOT_RUN`; live WB pull `BLOCKED_EXTERNAL_MUTATION` |
| `/app/ff/fbs`, `Состав` | 4 visual stages; print pick list; start work | лист подбора/тележка | STATIC; `NOT_RUN` |
| `/app/ff/fbs`, `Подбор` | scan cell, scan product; открыть доступные ячейки; `Снять N шт.`; undo/return where exposed | товар, сканер, ячейка | STATIC; `NOT_RUN` |
| `/app/ff/fbs`, `Упаковка и маркировка` | ТЗ, QR order sticker, ЧЗ/ШК print dialog, reprint menu, bulk print, pack all | один заказ, упаковка, два типа принтера | STATIC; `NOT_RUN` |
| `/app/ff/fbs`, `Короба` | add N boxes, expand/collapse, assign items/search/qty, remove, PVZ QR preview, clear/delete menu, deliver, supply QR after success | закрываемые физические короба | STATIC; `NOT_RUN` |
| `/app/ff/fbs/stock-sync`, section `Остатки WB` | seller/warehouse/search/refresh; add binding; enable/disable row; sync one/all; background status | административная привязка, не складская сборка | UI_CLICKED: Stocks, seller selected, empty bindings, reload retains tab. Binding/export/sync `BLOCKED_EXTERNAL_MUTATION` |

## FF portal — Честный знак, движения и интеграции

| Маршрут | Действия | Runtime/ограничение |
| --- | --- | --- |
| `/app/ff/honest-sign` | карточки личного/общего пула, брак, на исходе; seller/search/filter/pagination; загрузить КМ; расходная лента; открыть pool/product | VISUAL PASS_EMPTY 1280+1920; actions `NOT_RUN` |
| `/app/ff/honest-sign/pool/:poolId` | фильтр кодов, reserve/print/defect where allowed, pagination/back | STATIC; `NOT_RUN`; полные КМ не скриншотить |
| `/app/ff/honest-sign/product/:productId` | продуктовые пулы/codes, print/reprint/defect, back | STATIC; `NOT_RUN` |
| `/app/ff/honest-sign/ledger` | фильтры и расходные записи/export | STATIC; `NOT_RUN` |
| `/app/ff/honest-sign/reprints` | очередь перепечаток, открыть контекст/повторить разрешённое действие | STATIC; `NOT_RUN` |
| `/app/ff/honest-sign/import` | выбрать seller/product/file, preview, import | STATIC; `NOT_RUN`; shared pool mutation blocked |
| `/app/ops` | redirect на `/app/ops/inbound` | STATIC |
| `/app/ops/inbound` | legacy список/draft/detail операций inbound | STATIC; `NOT_RUN` |
| `/app/ops/outbound` | legacy outbound create/detail/pick/ship | STATIC; `NOT_RUN` |
| `/app/ops/movements` | refresh, start digest, poll/result | STATIC; `NOT_RUN` |
| `/app/ops/transfers` | source/destination/product/qty, submit | STATIC; empty submit `NOT_RUN`, реальный transfer `BLOCKED_SHARED_DATA` |
| `/app/integrations/wb` | seller, status, secret fields save/clear, cards/supplies sync, link product, imported lists | STATIC; credential forms runtime intentionally not opened |
| `/app/ff/inbound`, `/app/ff/outbound`, `/app/ff/warehouses`, `/app/ff/integrations/wb` | legacy redirects | STATIC |
| unknown `/app/*` | wildcard в dashboard | STATIC; Browser `NOT_RUN` |

## Seller portal

Актуальный sidebar содержит прямые пункты `Документы`, `Товары`, `Честный знак`, `Настройки`, notification bell и logout. Оркестратор открыл четыре основных routes в stable desktop viewport; product reviewer лично просмотрел каждый screenshot. Discrepancy CTA и сохранение inbound draft реально выполнены; остальные действия не засчитываются автоматически.

| Маршрут | Действия селлера | Физический/бизнес-результат |
| --- | --- | --- |
| `/seller/` | redirect в `/documents` после входа | рабочий стол селлера |
| `/seller/documents` | type/sort; create inbound; create MP unload; request correction; open row/modal; refresh | UI_CLICKED list; discrepancy CTA runtime FAIL; inbound/MP draft readback visible; filters/rows/refresh partly `NOT_RUN` |
| `/seller/inbound/new` | дата, planned boxes, add/search products, qty, delete, save draft, submit to warehouse | WORKFLOW empty draft save → Documents row; products/delete/submit/reload/failure `NOT_RUN` |
| `/seller/inbound/:requestId` | продолжить draft, изменить разрешённые поля, submit/reload | тот же документ без потери прогресса |
| `/seller/products` | sync products, search/pagination, FBS/stock-sync switches, packaging instruction | ассортимент и доступность одного seller scope |
| `/seller/honest-sign` | личные/общие остатки, брак, загрузка, ledger-related navigation | обеспечить маркировкой свои товары |
| `/seller/settings` | интеграционные status cards и разрешённые настройки | подключить seller account; секретные формы не входят в runtime-аудит |
| `/seller/notifications` | list, mark read/read all, reload | обработать события своих документов |
| unknown `/seller/*` | wildcard в `/documents` | безопасный возврат |

## Mobile/ТСД — static inventory

Mobile repo находится на указанном HEAD, но поверх него есть чужие modified/untracked файлы. Поэтому маршруты ниже — inventory текущего dirty snapshot; визуальное качество и фактическая сборка имеют `NOT_RUN`.

| Route | Экран | Интерактивные элементы и физический цикл | Runtime |
| --- | --- | --- | --- |
| auth | login/password | saved staff tile; PIN keypad digits/back/confirm; password login; expand/collapse server settings; set/confirm PIN | `NOT_RUN` |
| `home` | три большие очереди | `Приёмка`, `Сортировка`, `Отгрузка`, count badge, `Сменить` сотрудника | `NOT_RUN` |
| `inbound` | очередь приёмки | pull-to-refresh, retry, open card, back | `NOT_RUN` |
| `inbound/{id}/boxes` | короба | add box; select box; icon «отметить этикетку как напечатанную»; delete empty + confirm; go to receiving; back | `NOT_RUN` |
| `inbound/{id}/receiving?boxId=` | поштучный пересчёт | scan box/item; loose mode; open boxes; tap line/manual qty; close box + confirm; complete summary + confirm; retry/back | `NOT_RUN` |
| `sorting` | очередь размещения | pull-to-refresh, retry, open card, back | `NOT_RUN` |
| `sorting/{id}` | размещение | scan/select box or loose product; scan location; cancel target; qty; confirm placement; finish + confirm | `NOT_RUN` |
| `outbound` | очередь отгрузки | pull-to-refresh, retry, open card, back | `NOT_RUN` |
| `outbound/{id}` | assembly + packaging | add/select box; scan location/product; close; line progress; pack line/manual qty/confirm shelf; complete packaging; ship; discrepancy confirm; retry/back | `NOT_RUN` |

Отдельный static product-risk candidate: на mobile inbound box screen кнопка с иконкой принтера вызывает действие `markLabelPrinted`, то есть в изученном коде отмечает факт печати, а не доказывает физическую печать. Пока экран/принтер не пройдены на устройстве, это не visual finding, но процесс нельзя считать завершённым.

## Необнаруженные пользовательские маршруты

- отдельный полноценный billing/invoice portal;
- завершённая веб-инвентаризация;
- отдельный FF UI для просмотра состояния всех background workers/job queues без привязки к конкретной функции.

Они обозначены как GAP/candidate, а не как придуманные требования: inventory прямо присутствует в nav, billing упомянут действующими документами/настройками, background status необходим существующим sync/digest действиям.
