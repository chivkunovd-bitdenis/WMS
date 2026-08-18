# Батч 06. Handoff оркестратору

## Короткий ответ

B06 закончен как evidence-backed review core FF-упаковки, но продуктовый процесс получает **STOP перед самостоятельным массовым пилотом**. Транзакционное ядро корректно сохранило товар: B total2 осталось в cell A1.1 и только split изменился `unpacked2/packed0→unpacked1/packed1`; double-click pack/complete не дал дубля. Но упаковщик не может безопасно выбрать задание, увидеть seller/warehouse/TЗ, сканировать факт по единице, исправить ошибку или открыть выполненный документ после reload.

## Что реально выполнено

- Настоящий in-app Browser на Railway staging; standard 1280×720 DPR1.
- Runtime wide 1920×1080 DPR1, но export физически1873×1080; exact1920 PNG не заявлен.
- Baseline A/B unpacked/packed прочитан в UI до mutation.
- Populated open queue11, pending marking13, safe print preview and no-print close/reload.
- Create dialog: exact/foreign warehouses inventory, Sorting/A1.1, populated three-product place, auto-selection, deselect, zero/negative/blank/decimal/text/overage, Cancel/reopen.
- Safe manual task №000020 B qty1: double-click create, queue/reopen/reload, prepack stock, pack double-click, progress close/reopen, stock split read-back, complete double-click, terminal read-only and final stock.
- Manual A task №000019: created without progress; cancel native dialog hit documented IAB blocker, subsequent queue/pending/stock read-back captured.
- Back/Forward and queue reload performed.
- Saved PNG31; personally opened via `view_image`:31/31; each has visual verdict.
- Checklist138/138 adjudicated;105/138 fully executed. Remaining outcomes are explicit:13 `NOT_RUN`,11 `N/A`,6 `BLOCKED_ENV`,3 `BLOCKED_FIXTURE`.

## Checklist counts

- `PASS`:68.
- `FRICTION`:11.
- `FAIL_PROCESS`:16.
- `FAIL_UX`:10.
- `BLOCKED_FIXTURE`:3.
- `BLOCKED_ENV`:6.
- `NOT_RUN`:13.
- `N/A`:11.
- Total:138.

## Operator-flow measurements

### Создать B1 из A1.1

Фактический простой путь в текущем UI: **9 inputs / 9 attention shifts / scanner0**.

1. Create.
2. Open/select warehouse.
3. Open/select location.
4. Compare three product rows without seller.
5. Deselect A.
6. Deselect shared SKU.
7. Change B qty2→1.
8. Create.
9. Re-orient in task.

Основная лишняя цена — не сами dropdown, а обязанность помнить seller и вручную снять auto-selected чужие строки.

### Выполнить one-unit task из queue

Минимум **4 inputs / 7 attention shifts / scanner0**: click mouse-only row → horizontal join identity/action → click `Упаковать` → click `Завершить`. Между ними оператор переключает внимание queue→number→product/place→physical item→right-side CTA→progress→complete.

Минимальный безопасный путь в тех же сущностях: open/scan task → scan cell → scan product (`+1`, auto-focus) → final confirm: **4 events / 4 attention shifts** для одной единицы. Для нескольких единиц повторяются только product scans; dropdown и `+N` остаются fallback.

## Главные stop-gates

1. Queue не показывает seller/warehouse/cell/product/progress; rows mouse-only.
2. Create auto-selects maximum всех SKU места, не показывает seller и смешал exact synthetic строки с shared product.
3. Persisted seller ТЗ отсутствует на create/task work surface.
4. Нет task/location/product scan, unit progress, decrement/undo/manual +N; button проводит весь remainder.
5. Decimal1.9 silently floor→1; zero/negative/blank получают общий banner вместо row/focus.
6. 1280 table не показывает identity и CTA одним взглядом.
7. Done/cancelled history и stable detail route отсутствуют; после reload №000020 недоступен.
8. Marking pool0 блокирует Print без recovery/owner/next step; raw `__SORTING__` остаётся в operator UI.

## Что работает

- Exact place/warehouse isolation при create выдержана; foreign state не мутирован.
- Create не меняет packed/unpacked до физического pack.
- Overage create qty rejected with understandable error.
- Create/pack/complete double-click did not duplicate visible task or stock movement.
- Pack converted exactly one B unit in same place; total/cells/available conserved.
- Progress durable across close/navigation/reload/reopen.
- Premature complete blocked; terminal controls become read-only.
- Pending marking count/read-back and safe no-print preview durable.

## Final staging state для B07

- Seller: `B01 UX Seller 960724`.
- Warehouse: `FBS WB 1155120`.
- Cell: `A 1.1`, barcode `LOC-36F984B31C3D`.
- A `B02-UX-35204480-A`: total3, unpacked3, packed0, Sorting0, cells3, available3; persisted ТЗ, requires ЧЗ; no available synthetic КМ.
- B `B02-UX-35204480-B`: total2, unpacked1, packed1, Sorting0, cells2, available2; persisted ТЗ; non-ЧЗ task line.
- Task №000020: visible terminal `Выполнено`, manual, B qty1, no unload; after reload not available in UI and technical ID not visible.
- Task №000019: no progress; absent from final open queue, A stock unchanged. Exact native cancel branch remains `BLOCKED_ENV`.
- Final open packaging queue11; pending marking13.
- Current Browser route `/app/ff/packaging`, 1280×720 DPR1, session active.
- No rollback UI exists for packed→unpacked; B1 packed is deliberate synthetic final state and must not be mistaken for initial baseline in B07.

## Непокрыто и blockers

- Empty open queue/location blocked by populated connected tenant and absence of filters.
- Native cancel confirm exact accept/reject screenshot blocked by IAB dialog-control event.
- Fully packed ЧЗ completion/reprint/defect blocked by no isolated available/printed КМ; real/external marking prohibited.
- Dirty task input, per-line zero/decimal/blank/over scan are N/A because no scan/manual qty surface exists.
- Wide task/create panels, Enter-in-qty, leading-zero/huge and mixed valid+invalid submit not run.
- Existing MP-linked packaging rows were inventoried (`Да`) but not opened/executed; B07 owns that path.

## Gate

Evidence gate: **`ACCEPTED`** —138/138 IDs terminally adjudicated,31/31 PNG visually reviewed, safe core mutation read back, all gaps named. `ACCEPTED` относится к полноте evidence ledger, а не к готовности продукта; явные blockers остаются blockers.

Product gate: **`STOP`** before independent mass use. Transaction conservation alone does not compensate for task-selection, cross-seller create, missing ТЗ, scanner/unit flow and audit-history failures.

## Git boundary

B06 application code and `MASTER_PRODUCT_UX_REVIEW_RU.md` не менял, commit/push не выполнял и чужие изменения не откатывал. Добавлены только B06 review docs/evidence; оркестратор должен интегрировать их отдельным scoped review commit.
