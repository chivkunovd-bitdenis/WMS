# F09/F10 Product UX verdict after F08

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Product/UX Review Agent.
Режим: read-only product review; код не редактировался.

## Mandatory checks

- `git rev-parse --show-toplevel` -> `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
- Прочитан `AGENTS.md`.
- Прочитан `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
- `git status --short --branch` показал грязное дерево до начала review; существующие изменения не трогались.

## Sources reviewed

- `docs/reviews/product-operations-ux/2026-08-12/ITERATION_BA_FEATURE_SPEC_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/ITERATION_FEATURE_CARDS_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/f08-browser-product-qa-final/F08_BROWSER_PRODUCT_QA_FINAL_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/f22-product-review/F22_PRODUCT_VERDICT_SAFE_STOCK_SYNC_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/f22-browser-product-qa-final/F22_BROWSER_PRODUCT_QA_FINAL_REPORT_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/f23-product-design-rereview/F23_PRODUCT_DESIGN_REREVIEW_RU.md`
- `backend/app/services/stock_direction_service.py`
- `backend/app/api/inventory_balances.py`
- `backend/app/services/fbs_stock_availability_service.py`
- `backend/app/services/fbs_stock_sync_service.py`
- `backend/app/services/marketplace_unload_service.py`
- `frontend/src/screens/v2/SellerProductsStockScreen.tsx`
- `frontend/src/screens/v2/FfProductsCatalogScreen.tsx`
- `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
- `backend/tests/test_stock_directions.py`
- `backend/tests/test_fbs_stock_sync.py`
- `frontend/tests-e2e/seller-stock-directions.spec.ts`

## F09. Свободный FBO остаток

Verdict: `PRODUCT_APPROVED_FOR_DEV`.

F09 похожа на реальный складской процесс и не требует возврата в BA. Селлер заранее распределяет общий остаток по бизнес-направлениям: FBS-пул, наборы, прочие резервы. FBO/MP-отгрузка должна брать только то, что осталось свободным после этих распределений и активных отгрузочных резервов. Это не новый рабочий экран, а правило доступности товара в уже существующей отгрузке на МП плюс понятное отображение свободного FBO в текущих местах.

После F08 базовая UX-модель уже есть: seller drawer показывает `FBS`, `Резервы`, `Свободный FBO`; FF catalog показывает компактный distribution popover без отдельной колонки `Лимит`, bulk-шумов и технических кодов. F09 должна переиспользовать эту модель, а не добавлять второй способ распределения.

Required dev scope:

1. Сделать единый расчет для FBO/MP availability: товар доступен для новой отгрузки только в размере свободного FBO остатка с учетом уже активных MP/outbound резервов.
2. Развести два пользовательских смысла, даже если backend хранит их рядом: `Свободный FBO` = общий физический остаток минус FBS-пул/резервы/наборы; `Доступно к отгрузке` = свободный FBO минус активные резервы других FBO/MP документов.
3. В MP/FBO picker показывать только товары с положительным доступным количеством для новой строки; для уже добавленной строки сохранять видимость товара, но валидировать увеличение количества по текущему доступному остатку с исключением текущего документа.
4. При превышении количества показывать человеческую ошибку: `Недостаточно свободного FBO остатка. Уменьшите количество или освободите резерв/FBS-пул.`
5. Обновить/закрепить тесты на пример `1000 всего -> 200 FBS + 300 резервы -> 500 свободно FBO`, плюс negative case, где MP/FBO line больше свободного остатка не проходит.

Required visible data:

- SKU/название товара в существующей строке или picker.
- `FBS N шт`, `резервы N шт`, `Свободный FBO N шт` в существующем drawer/popover.
- В MP/FBO выборе товара: короткое `доступно N` или `доступно для FBO N`, если ширина позволяет без раздувания.
- В ошибке: что именно не хватает и какое действие поможет.

Unneeded fields:

- Формула `total - directions - reserves` в основной таблице.
- Отдельные технические суммы `direction_total`, `fbs_reserved`, `mp_reserved`, ids резервов или названия backend-моделей.
- Новый экран распределения только ради F09.

States:

- Empty: если свободного FBO нет, в MP/FBO picker нет доступных SKU и виден простой текст `Нет свободного FBO остатка для отгрузки`.
- Error: превышение доступного FBO не сохраняет строку/план и объясняет, что нужно уменьшить количество или освободить распределение.
- Success: строка MP/FBO добавлена или документ запланирован, доступное FBO количество уменьшается, FBS-пул не меняется.

Forbidden UI noise:

- Новые чипы по каждому резерву в основной таблице.
- Raw formula, raw enum, ids складских резервов.
- Дублирующая кнопка управления FBS/FBO рядом с F08 drawer.
- Колонка `Лимит` или любой возврат к старому F23 seller catalog перегрузу.

Conflict check:

- With F08: no conflict if F09 only consumes F08 distribution and opens the same drawer/popover for adjustment.
- With F23: no conflict if seller catalog stays compact and F09 does not re-add `Лимит`, global bulk actions, raw sync states or extra regular chips.

## F10. FBS sync publishes only FBS pool

Verdict: `PRODUCT_APPROVED_FOR_DEV`.

F10 можно отдавать в atomic dev сейчас, но только как узкую sync/availability фичу поверх F08/F22 guardrails. Продуктовое правило достаточно четкое: WB получает не общий остаток товара на ФФ и не свободный FBO, а только явный FBS-пул, уменьшенный на активные FBS-резервы. Если явного FBS-пула нет, WMS не знает безопасное FBS-количество и не отправляет в WB `0` как fallback.

Важное ограничение: F22 browser QA на момент review не passed полностью. Negative safe-zero path прошел, backend positive readback `7` прошел, но seller UI после confirmed readback показал `Ошибка WB`. Поэтому F10 можно начинать как dev-scope, но нельзя считать F10 accepted/done или выпускать sync клиентам без живого browser QA, где positive FBS-pool publish показывает человеку подтвержденное состояние.

Required dev scope:

1. FBS availability formula: `publishable_fbs = explicit_fbs_pool - active_fbs_order_reservations`, clamped at zero, scoped by seller + WMS warehouse + WB warehouse mapping.
2. Publish plan must never use total FF stock, `available`, free FBO, old `fbs_stock_limit`, stale sync item, missing dict key or exception as source of WB amount.
3. Missing FBS-pool, unknown availability, missing mapping/token, WB error and readback mismatch must be fail-closed: no WB `PUT 0`, no success state, last confirmed amount unchanged.
4. Positive path: if FBS-pool is `N > 0`, WB publish sends `N` after FBS reservations/allowed cap, then success appears only after WB readback confirms the same value.
5. Explicit zero is not required for F10. If dev chooses to support `0`, it must be a separate F22-safe dangerous action with clear confirmation like `Отправить в WB 0 шт`; otherwise `0` stays blocked/not sent.
6. The known F22 UI mismatch must be resolved before F10 browser acceptance: after confirmed readback the seller UI must show `WB: N шт` or another approved compact confirmed/pending-safe state, not `Ошибка WB`.
7. Add tests that prove `1000 total + 200 FBS-pool -> WB target 200`, FBS order reservation decrements only that FBS pool, missing pool does not send zero, and WB/readback error does not look successful.

Required visible data:

- In seller catalog row: compact `FBS N шт` and compact publication state.
- In drawer: `FBS-пул для публикации в WB` as the place to set the pool.
- In publication state: `Нет FBS`, `Пауза`, `Проверяем WB`, `WB: N шт`, `Ошибка WB` or equivalent human wording.
- Optional detail can show last confirmed WB amount, but only without widening the row.

Unneeded fields:

- `Лимит` as a visible table column, field or chip.
- Raw backend statuses: `unsafe_stock_unknown`, `unsafe_zero_blocked`, `pending_confirmation`, `warehouse_mapping_missing`, `wb_upstream_error_*`, `readback_mismatch`, `conflict`.
- Raw JSON, stack traces, token/mapping internals or chrtId debug text in the main UI.
- A second publication mechanism outside the existing seller catalog/drawer flow.

Safe behavior when FBS-pool is absent:

- Row shows `Нет FBS` or `FBS-пул не выделен`.
- Toggle/publish action is disabled or skipped with human explanation.
- Bulk enable skips that row and returns a selected-only result with reason; it must not produce whole-catalog side effects.
- Backend creates no publish target with `amount=0`.
- WB stock remains unchanged, including when previous WB readback was nonzero.

States:

- Empty: no FBS-pool means `В WB не отправлено` / `Нет FBS`, with path `Настроить FBS-пул`.
- Error: WB/mapping/token/readback problem is shown as human `Ошибка WB` or `Не отправлено`, without raw code and without changing confirmed value.
- Success: only after readback; show `WB: N шт` or equivalent confirmed amount.

Forbidden UI noise:

- `Лимит` anywhere in the seller product table.
- Global `Включить всем` / `Выключить всем` without explicit row selection.
- Long technical statuses in row body.
- Multiple chips for normal states.
- Any wording that implies WB received `0`, `N` or success before readback.

Conflict check:

- With F08: no conflict if F10 reads the FBS direction as source of truth and sends users to the same stock direction drawer to configure it.
- With F22: F10 must preserve F22 fail-closed behavior. F10 dev must not weaken safe-zero blocking or introduce fallback zero.
- With F23: no conflict if compact seller catalog remains the main surface and F10 does not reintroduce `Лимит`, raw technical states or unselected whole-catalog actions.

## Verdict matrix

| Feature | Verdict | Can go to atomic dev? | Needs BA rework? | Main dependency/risk |
| --- | --- | --- | --- | --- |
| F09 | `PRODUCT_APPROVED_FOR_DEV` | Yes | No | Keep it as availability rule + existing F08 UI; no new FBO distribution UI. |
| F10 | `PRODUCT_APPROVED_FOR_DEV` | Yes | No | Must preserve F22 fail-closed sync; F22 positive UI mismatch must be fixed before acceptance/browser pass. |

## Status after this review

- local: evidence document created under the allowed folder.
- committed: этот артефакт должен быть единственным файлом в scoped commit; SHA указывается в финальном ответе.
- pushed: no, by instruction.
- deployed: no, by instruction.
- browser-tested: no; this is Product/UX review only, not Browser Product QA.
- remaining risks: existing dirty worktree contains unrelated modified/untracked files; this review must be committed with scoped git add only.
