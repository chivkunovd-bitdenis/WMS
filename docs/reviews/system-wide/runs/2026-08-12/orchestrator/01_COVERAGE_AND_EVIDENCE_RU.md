# Покрытие и доказательства

## Визуальное покрытие

| Контур | Проверено глазами | Уровень доказательства | Остаток |
|---|---|---|---|
| FF navigation | Dashboard, MP, FBS, reception, sorting, packaging, cells, sellers, catalog, inventory, Honest Sign, settings | `UI_CLICKED` на staging, 1280 batch и stable 1920 batch | populated states не везде доступны |
| Cells | warehouse create, two cell creates, reload, warehouse reselect, обе ячейки на PNG | `WORKFLOW_WITH_RELOAD` | delete/print/error не пройдены |
| MP shipment | create empty draft, delayed result, reload, reopen detail | `DURABLE_DRAFT` | lines/reservation/pack/box/submit/ship не пройдены |
| Seller documents | four routes, discrepancy CTA, empty inbound draft create | `UI_CLICKED` + `DRAFT_CREATED` | submit/receive/discrepancy resolution не пройдены |
| FBS | 5 order groups, WB-stock tab, reload | `READ_ONLY_UI` | domain mutation blocked by live-WB boundary |
| Inventory | route opens only placeholder | `CONFIRMED_GAP` | весь процесс отсутствует в UI |
| Mobile | static source/contracts only | `STATIC_REVIEW` | device/scanner/printer runtime `NOT_RUN` |

## Ключевые изображения

- `UI-FF-DASHBOARD__synthetic-admin__1920x1080__stable-2s.png`
- `UI-FF-FBS__synthetic-admin__1920x1080__stable-2s.png`
- `UI-FF-INVENTORY__synthetic-admin__1920x1080__stable-2s.png`
- `UI-FF-CELLS__warehouse-and-cells__1920x1080__reload-reselect-visible.png`
- `UI-FF-MP-SHIPMENTS__create-draft__1920x1080__reload.png`
- `UI-FF-MP-SHIPMENTS__draft-detail__1920x1080__opened.png`
- `UI-SELLER-DOCUMENTS__discrepancy-action__1920x1080__clicked.png`
- `UI-SELLER-INBOUND__empty-draft__1920x1080__result.png`
- `UI-SELLER-SETTINGS__existing-test-seller__1920x1080__stable-2s.png`
- `UI-FF-FBS__wb-stocks__1920x1080__stable.png`

Полный каталог находится в соседнем `evidence/`. Ранние файлы `clicked` с переходной геометрией не используются как подтверждение layout-дефекта, если есть соответствующий `stable-*`.

## Runtime-проверки вне Browser

- Конкурентное завершение одной приёмки: architect `2/2`, teamlead независимо `2/2`; каждый раз два HTTP 200, документ `actual=1`, остаток `2`, два движения по `+1`.
- Background job probe: ручная job заканчивается через FastAPI inline fallback, но отдельный worker/beat отсутствует; periodic execution не доказан и по deployment inventory невозможен.
- Deployment identity: `web` и `WMS` совпадают по SHA `44fe72e…`; worker identity отсутствует; schema только inferred.

## Статическое покрытие

Инвентаризированы 377 tracked backend files, 259 frontend files и 71 mobile file в pinned mobile commit. Отдельные role-ledgers уточняют статус по API/services/models/migrations/tests/routes. `REVIEWED` в статическом ledger означает прочитанный контур и проверенные риски, а не доказанный рабочий пользовательский процесс.
