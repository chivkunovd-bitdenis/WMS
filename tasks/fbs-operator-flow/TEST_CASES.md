# Test cases — FBS operator flow

> **Permanent IDs:** `TC-S17-001` … `TC-S17-024` in `docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md` §S17 (FBSFLOW-130).

| ID | Сценарий | Ожидаемый результат | Негатив / ограничение |
|---|---|---|---|
| TC-01 | Три селлера на одном WMS-складе | Для каждого создаётся отдельная поставка; seller data isolated | Заказы/остатки/КИЗ другого seller недоступны |
| TC-02 | Разные WB warehouses | Preflight показывает конкретные несовместимые rows | Create не вызывается |
| TC-03 | B2C + B2B | Набор incompatible | Никакой частичной поставки |
| TC-04 | Разные cargo type | Набор incompatible | Первый заказ не должен молча определять supply после неверного selection |
| TC-05 | PVZ + can_pvz=false | PVZ disabled, row reason visible | warehouse/sc остаётся допустимым вариантом |
| TC-06 | Atomic create | Один API call WMS создаёт WB supply и подтверждённый состав | timeout не создаёт false success или duplicate |
| TC-07 | Scan picking | location → product picks earliest eligible order | wrong location/product returns exact error |
| TC-08 | Multi-operator picking | Два клиента видят одинаковый progress после refresh/poll | stock=1 concurrent scan gives one success |
| TC-09 | Undo picking | До pack товар возвращается в source location | После pack undo blocked |
| TC-10 | Existing packaging | Picked item упакован через PackagingTask; inventory unpacked→packed | FBS local checkbox cannot mark packed |
| TC-11 | Same SKU, two orders | Two physical pack operations fulfill two exact WB orders | Third pack rejected |
| TC-12 | KIZ from manufacturer | Scanner raw GS code binds to order and WB accepts | Lost GS causes visible rejection |
| TC-13 | KIZ from seller pool | Only seller/product code reserved, printed, applied, checked | duplicate/cross-seller code rejected |
| TC-14 | Metadata gate | Missing/rejected required blocks; WB allowed intermediate continues | local product flag cannot override WB |
| TC-15 | One order sticker | Real PNG preview 58×40 and print available | missing file is not ready |
| TC-16 | Batch stickers | ready/missing/failed counts and retry missing only | no empty print page |
| TC-17 | PVZ cargo places | Count creates WB trbx; each has printable QR | no order→trbx mapping required |
| TC-18 | PVZ dimensions | side/sum/weight/volume blockers are explicit | missing dimensions require audited confirmation |
| TC-19 | Delivery checklist | Fresh sync + all common and route blockers visible | stale checklist cannot deliver |
| TC-20 | PVZ deliver | trbx + QR ready, WB confirms, local in_delivery | timeout → pending_confirmation |
| TC-21 | Warehouse/SC deliver | no trbx required; after success QR supply available | QR trbx never shown as required |
| TC-22 | Partial acceptance | Exact accepted/rejected orders, reasons, remaining deadline | supply is not flattened to generic success |
| TC-23 | Full compose run | Browser/API → backend → queue → PostgreSQL → emulator | emulator does not prove current live WB contract |
| TC-24 | Live WB smoke | Exact request contracts checked on sandbox/test cabinet | run only with explicit secrets/authorization |

## Обязательные frontend browser paths

1. Worklist enrichment + live deadline.
2. Selection blockers + supply summary + atomic create.
3. Full-screen workspace stages and blockers.
4. Persistent picking with reload and second context.
5. Embedded existing PackagingTask.
6. Marking row state and rejected required metadata.
7. Sticker preview without empty page.
8. PVZ cargo places + all QR.
9. Warehouse/SC QR supply.
10. WB timeout/409 does not show local success.

