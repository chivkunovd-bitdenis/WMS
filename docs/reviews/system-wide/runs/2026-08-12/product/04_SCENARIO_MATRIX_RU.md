# Матрица продуктовых сценариев и coverage ledger

## Как читать coverage

`UI_CLICKED` означает, что оркестратор реально использовал элемент в staging Browser, а product reviewer лично просмотрел result screenshot. `WORKFLOW` требует связки действия и бизнес-результата; при наличии reload это указано отдельно. `NOT_RUN` не заменяется чтением JSX/API. `BLOCKED` означает осознанную границу: внешний WB, shared stock, секреты, отсутствующая роль/fault fixture или mobile device.

Runtime evidence относится к staging revision `44fe72e`; static inventory — к эталону `a39530c`. Отдельный worker в staging отсутствует, schema revision лишь inferred.

## Сводный ledger

| Coverage class | Что реально покрыто |
| --- | --- |
| `UI_CLICKED` | 12 FF sidebar destinations; 4 seller destinations; FBS 5 status tabs и `Остатки WB`; discrepancy CTA; warehouse/cell forms; manual product form; seller inbound create/save; MP draft create/open/reopen |
| `WORKFLOW` | warehouse + 2 cells create → reload → reselect → обе cells + sorting; catalog required-seller validation → no false create after reload; seller empty inbound draft save → Documents readback; FF empty MP draft create → detail → reload → reopen → seller readback; discrepancy CTA → explicit placeholder error |
| `NOT_RUN` | auth failure/logout; populated reception/sorting/packaging; FBS order selection и весь supply workspace; MP lines/plan/pack/boxes/ship; inventory process; Honest Sign actions; notifications; seller product sync/ЧЗ/settings mutations; legacy ops/transfers; billing; весь mobile runtime |
| `BLOCKED` | live WB pull/export/bindings/stock sync; shared-stock mutations; secret forms/credentials; destructive address-storage toggle; fault injection без fixture; FF-staff role checks; mobile device screenshots; worker/schema alignment |

## Матрица normal/empty/error/retry/reload/partial

| Процесс | Normal/action | Empty | Error/failure | Retry | Reload | Partial | Итог |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Public auth/login/logout | seller login result visual | N/A | NOT_RUN | NOT_RUN | NOT_RUN | N/A | доступ доказан, полный auth lifecycle нет |
| FF shell/menu | 12 menu clicks | N/A | wildcard NOT_RUN | N/A | route reload partly | N/A | `UI_CLICKED`; stable 1280/1920 ключевых screens |
| Dashboard | empty screen visual | queues empty | internal `submitted` = FAIL_TERM | N/A | NOT_RUN | row click NOT_RUN | P2 PROD-003; bad MP URL only static candidate |
| FBS order groups | 5 tabs clicked | PASS_EMPTY groups | NOT_RUN | external refresh/pull BLOCKED | Stocks tab retained | selection NOT_RUN | navigation covered, physical process not covered |
| FBS supply creation/composition | NOT_RUN | N/A | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | no isolated compatible orders |
| FBS picking | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | scanner/manual path static only |
| FBS packing/marking | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | print/pack static only |
| FBS boxes/deliver | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | external/shared mutation blocked |
| FBS WB stocks | tab + seller clicked | no active bindings visual | external mutation blocked | NOT_RUN | PASS active tab | N/A | read-only screen covered only |
| Reception | screen clicked | PASS_EMPTY | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | no isolated inbound stock |
| Sorting/putaway | screen clicked | PASS_EMPTY | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | no isolated accepted stock |
| Packaging | screen clicked | PASS_EMPTY | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | populated task unavailable |
| MP unload | create empty draft, reopen | initial list empty | required downstream fields not attempted | NOT_RUN | PASS list/detail | plan 0/rows 0 | draft lifecycle/readback covered; shipment not covered |
| Catalog product | form filled | list empty | PASS native required seller validation | N/A | PASS no false create | values retained in dialog | validation workflow covered |
| Warehouses/cells | warehouse + 2 cells created | initial empty | NOT_RUN | N/A | PASS warehouse + cells after reselect | 2 physical + sorting | durable create workflow covered; print/delete absent |
| Sellers | row visual | N/A | NOT_RUN | N/A | NOT_RUN | N/A | list only |
| Inventory | no process | N/A | N/A | N/A | N/A | N/A | FAIL placeholder, PROD-001 |
| Honest Sign | hub clicked | zero pools visual | NOT_RUN | NOT_RUN | NOT_RUN | N/A | actions/role staff not covered |
| FF settings | controls visual | staff empty | destructive toggle BLOCKED | N/A | NOT_RUN | N/A | address toggle risk PROD-006 |
| Notifications/background | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | static only |
| Movements/transfers/legacy ops | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | shared stock mutation blocked |
| Seller documents | list and CTA clicked | N/A | discrepancy placeholder reproduced | N/A | cross-portal rows visible | inbound + MP rows | PROD-005 confirmed |
| Seller inbound | empty draft saved | 0 product lines | submit validation NOT_RUN | NOT_RUN | list readback, detail reload NOT_RUN | draft status | draft behavior allowed by contract |
| Seller products | route visual | 0 products/FBS 0 of 0 | sync not run, WB key absent | NOT_RUN | NOT_RUN | N/A | empty/status only |
| Seller Honest Sign | route visual | zero personal/shared | NOT_RUN | NOT_RUN | NOT_RUN | N/A | no marking mutation |
| Seller settings | status cards visual | WB key absent | secret forms excluded | N/A | NOT_RUN | N/A | credential status only |
| Seller notifications | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | N/A | no evidence |
| Mobile auth/inbound/sorting/outbound | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | no device screenshots; dirty snapshot static only |
| Billing | NOT_RUN | N/A | NOT_RUN | NOT_RUN | NOT_RUN | N/A | complete user route not found; candidate only |

## Что нельзя считать end-to-end

Cells — единственный складской master-data workflow с доказанным durable reload. MP и seller inbound дошли только до разрешённого пустого draft. Ни один физический товар не был принят, отсканирован, разложен, упакован, промаркирован или отгружен в isolated tenant. Поэтому сквозные `seller → FF → physical stock → marketplace`, FBS и mobile процессы остаются `NOT_RUN`, а не «пройдены по API».

UI synthetic tenant в основном пуст. Read-only API reconnaissance другого staging scope подтверждает наличие данных, но не может быть объединён с этими screenshots в один ложный workflow.
