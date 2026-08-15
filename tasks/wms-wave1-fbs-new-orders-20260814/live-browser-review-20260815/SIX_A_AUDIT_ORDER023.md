# 6a Audit — FBS New Orders / ORDER 023

Scope: `wave1-fbs-new-orders`, visible elements of `FBS -> Новые`.

Note: in this worktree `docs/WMS_GATE.md` has section 6 and then section 7; a literal `6a` subsection is absent. This audit applies the ORDER 023 rule: every visible element must have a task ID, otherwise it is removed or recorded as a proposal.

## Kept Elements

| Visible element | Task ID | Decision |
|---|---|---|
| Screen title `Заказы FBS` | GLOBAL-02 | Kept as the minimum screen anchor. |
| Icon near title | GLOBAL-02 | Kept only as the established screen/module marker; no extra status meaning. |
| Button `Забрать заказы из WB` | GLOBAL-03, GLOBAL-02 | Kept as the single primary WB-dependent action. It is not equal-weight with refresh. |
| Button `Обновить` | GLOBAL-02, GLOBAL-05 | Kept as a small secondary read-back action for live state refresh; demoted from equal-weight `Обновить данные`. |
| Module tab `Заказы` | GLOBAL-02 | Kept as current sub-section marker. |
| Status tabs `Новые`, `В работе`, `В доставке`, `Завершённые` | GLOBAL-01, GLOBAL-02 | Kept as human state groups; required to keep new orders separate from active/delivery/done. |
| Seller filter | FBS-17, FBS-14 | Kept because export/search operate over current filters and multi-seller worklist needs scoping. |
| Warehouse filter `Склад селлера / WB` | FBS-02, FBS-17 | Kept; exact requirement. |
| Search field | FBS-14, FBS-15, FBS-16 | Kept as one smart live search field. Separate `Найти` button was removed. |
| Search icon inside field | FBS-14, GLOBAL-02 | Kept as field affordance, not a separate action. |
| Button `Скачать Excel` | FBS-17, GLOBAL-02 | Kept; export uses selected rows or current filtered/search set. |
| Checkbox column and row checkboxes | FBS-16, FBS-19 | Kept for persistent selection and multi-order supply creation. |
| Column `Товар` | FBS-08, FBS-14, FBS-04 | Kept; contains photo and compact product name only. Category/color/size are not shown as a default row line. |
| Product photo thumbnail and hover preview | FBS-08 | Kept; exact requirement. |
| Product name | FBS-14, GLOBAL-02 | Kept; single-line with tooltip to avoid row expansion. |
| Blocker text under a blocked row | FBS-19, GLOBAL-01 | Kept only when selection is impossible; gives the operator the reason. |
| Column `Заказ и сканирование` | FBS-04, GLOBAL-02 | Kept after reducing the old passport column. |
| `WB №...` | FBS-04, FBS-19 | Kept as the order identifier used for supply creation/read-back. |
| `ШК: ...` | FBS-04, FBS-14, FBS-17 | Kept as the primary scan identifier. |
| `SKU ...` or seller article fallback | FBS-04, FBS-14, FBS-17 | Kept as the third working identifier. `nmId` and `chrtId` are not visible in the row. |
| Column `Селлер` | FBS-17, GLOBAL-02 | Kept for multi-seller worklist and export context; single-line with tooltip. |
| Legal-buyer caption | GLOBAL-01 | Kept only for legal orders because it changes operational handling. |
| Column `Склад селлера / WB` | FBS-02, FBS-17 | Kept; exact requirement. |
| `WMS: ...` line under WB warehouse | FBS-02 | Kept because physical picking happens in WMS warehouse while WB warehouse identifies seller/WB source. |
| Column `Создан WB` | FBS-03 | Kept; exact requirement. |
| `В сборке: ...` elapsed line | FBS-03 | Kept; replaces old 120h deadline text. |
| Empty state text | GLOBAL-01, GLOBAL-02 | Kept as the minimum recovery hint when filters produce no rows. |
| Busy text `Обновляем рабочий список...` | GLOBAL-01 | Kept only while loading to explain temporary state. |
| Error/sync/no-match/export alerts | GLOBAL-01, FBS-14, FBS-17, GLOBAL-03 | Kept because they report action outcomes or recoverable WB/search/export states. Positive search-match alert is not kept. |
| Selection bar count | FBS-16, FBS-19 | Kept so selected rows remain visible across filters/search/tabs. |
| `Показать выбранные` | FBS-16 | Kept because FBS-16 requires a way to inspect persisted selected rows and clear selection when filters/search/tabs hide them. |
| `Снять выбор` | FBS-16, GLOBAL-02 | Kept as the explicit exit from persistent selection. |
| `Сформировать поставку` | FBS-19 | Kept as the main next action after compatible selection. |
| Selected-orders dialog | FBS-16, FBS-19 | Kept as selection read-back before supply creation. |
| Create-supply dialog | FBS-19, GLOBAL-03 | Kept; server preflight and WB read-back happen here. |
| Partial rejection warning in workspace | FBS-19, GLOBAL-03, GLOBAL-01 | Kept; fixed so it remains visible after read-back outside composition stage. |

## Removed

| Removed element | Reason |
|---|---|
| Subtitle `Соберите совместимые заказы...` under title | No specific task ID; it described how to use the screen and duplicated the actual selection/supply actions. Removed under GLOBAL-02. |
| Separate `Найти` button | No longer needed after live search; removed under FBS-14/FBS-15/GLOBAL-02. |
| Positive search result alert `Найдено совпадений...` | FBS-15 requires highlight and scroll to the first match, but not a separate persistent banner. Removed as extra UI under GLOBAL-02. |
| Default visible category/color/size line in every product row | FBS-04 allows compact color/size only when needed to distinguish positions. The default line inflated rows and was removed; category/color/size remain in search/export data under FBS-14/FBS-17. |
| Visible `nmId` and `chrtId` in the row | These made the row a product passport; removed from the visible row under FBS-04/GLOBAL-02. |
| Equal-weight `Обновить данные` button | Demoted to small `Обновить`; ORDER 023 required a clear primary action. |

## Proposal / Out Of Scope

| Element | Proposal |
|---|---|
| Module tab `Остатки WB` | This belongs to FBS-01, which is explicitly out of scope and must not be touched by this agent. Leave for FBS-01 owner or integration-level navigation decision. |

## Result

No remaining visible element in `FBS -> Новые` is kept as an "improvement just in case". Elements are tied to `FBS-02/03/04/08/14/15/16/17/19` or `GLOBAL-01/02/03/05`, except the FBS-01 module tab recorded above as out of scope.
