# S09 UX_CONTRACT_AND_MOCKUPS - BLG-D06

## Source and decision

Backlog item: `BLG-D06` - "Скрывать архивные товары OLD/ по умолчанию".

An archived product is a catalog record whose `sku_code` begins with the literal `OLD/`. This is the existing archive marker; S09 neither changes it nor adds a second archival status. The operator must start ordinary catalog work with only current products, yet be able to deliberately inspect the archive without mistaking an old card for a current one.

The decision is a local catalog-list presentation rule. It has no write action, API/data-contract change, external call, scanner behaviour, pagination model or side effect. The oracle is the owner-approved backlog wording and incident I20: archive SKU sorting currently puts `OLD/` records at the beginning of a work list.

## Affected-surface inventory

| Surface | Scope | Touched zone and reason |
| --- | --- | --- |
| `S-01`, route `/app/catalog/products`, `ProductsScreen` | In scope | The catalog's search/filter line and its four-column product table are the ordinary list named by BLG-D06 and I20. |
| `WbProductPickerDialog` in FF inbound and marketplace-unload flows | Unchanged | This is a quantity-selection dialog with stock/draft eligibility rules. Including or excluding an archive there changes a separate fulfilment selection process and its negative cases; BLG-D06 has no approved behaviour contract for it. |
| `SellerWbProductPickerDialog` aliases in seller inbound and seller marketplace-unload flows | Unchanged | It reuses the picker contract above. No change is authorised merely because it shares catalog-row data. |
| Seller `SellerProductsStockScreen` product/stock list | Unchanged | It is a seller inventory and WB-sync surface with FBS controls, pagination and a wider column set; it is not the catalog search surface identified by the backlog. |
| Product detail panel and "Создать SKU" form on `S-01` | Unchanged | They are adjacent legacy zones, not archive filtering or archive identification. |

This inventory is deliberately narrow: it prevents an S18 implementation from silently spreading a catalog filter into pickers or seller stock screens. If a later Product or impact review decides that a picker must also suppress archived products, that is a new or expanded behaviour contract and a new surface entry, not an implicit extension of BLG-D06.

## Filter contract

The filter is in the existing predictable filter zone directly above the `S-01` table. It consists of the existing text search plus one `SelectField`.

| Control | Exact label and options | Default and reset | Result rule |
| --- | --- | --- | --- |
| Text search | `FilterBar` placeholder only: `Название, SKU, селлер или артикул WB`. This ui-kit component has no label or accessibility-name prop, so BLG-D06 does not introduce a visible label `Поиск` or make an accessibility-name promise beyond the existing component contract. | Empty on first open, reload and return to the route. The operator clears the text directly; that changes only the query. | Case-insensitive substring match over the current fields already searched by `S-01`: name, SKU, seller and WB vendor code. |
| Archive filter (`SelectField`) | Label: `Показывать`. Options: `Актуальные товары` (`active`), `Все товары, включая архив` (`all`), `Только архивные товары` (`archived`). | `Актуальные товары` on first open, navigation back to the route and browser reload. Selection is not persisted. There is no separate reset action in this scope: the operator clears the search directly and selects `Актуальные товары` when returning to the default view. | `active`: rows whose SKU does **not** start `OLD/`; `all`: every row; `archived`: only SKU beginning `OLD/`. Query and archive filter combine with logical AND. |

The visible result counter is `Найдено: N` and counts only rows after both filters. It does not disclose a hidden-archive total. `S-01` currently has no pagination; BLG-D06 must not invent one. If pagination appears in a later separate change, it must count and page the already filtered result set.

Changing either control clears the selected product if that product is no longer in the visible result set. Choosing `all` or `archived` is the explicit operator choice that can reveal an archived product; it never selects, edits or otherwise acts on a row by itself.

## Archived-row treatment

When an archive is revealed (`all` or `archived`), its existing literal `OLD/` SKU remains visible in the fixed `SKU` column. In the `Название` cell the row also receives one existing `StatusChip` with exact label `Архив` and neutral tone. Its hint is `Архивная карточка: не выбирайте для текущей работы без проверки истории.` The chip is information, not an action and not a fourth colour meaning. There is no row fill and no locally styled archive colour.

The archive indication is intentionally redundant: the immutable-looking `OLD/` identifier remains available for audit, while the short neutral chip makes the archive state identifiable when a long name is truncated. No new component is needed, so there is no `DESIGN_SYSTEM_GAP`.

## Table and long-data rules

The table keeps its current four business columns and their order: `SKU`, `Название`, `Объём`, `Селлер`. The only new visible content is the archive chip inside the existing `Название` cell when the row is archived. No action column, modal, tab, print action, scanner line or additional status is introduced.

| Column | Width | Long-data treatment |
| --- | ---: | --- |
| `SKU` | 180 px | One line; full SKU is available in a tooltip when constrained. |
| `Название` | 360 px | `TextCell`-style one-line ellipsis with a tooltip containing the full product name; the neutral `Архив` chip remains visible next to the truncated text. |
| `Объём` | 120 px | One line, existing display value or `-`. |
| `Селлер` | 220 px | One-line ellipsis with a tooltip containing the full seller name. |

The table has `min-width: 880px`, a sticky header and horizontal scrolling in its own table container on narrow viewports. Filter controls remain above the table and never move into a row or a menu. On a narrow viewport the `FilterBar` stacks the search field and archive selector vertically at full available width; the table itself scrolls horizontally rather than squeezing, wrapping or hiding identifier columns.

## Text mockups

### Wide desktop: default current catalog

```text
Товары (SKU)
Таблица SKU, детали, создание и привязки

[ Название, SKU, селлер или артикул WB ] [ Показывать: Актуальные товары v ]  Найдено: 248

| SKU                | Название                                  | Объём | Селлер             |
| ART-402            | Футболка базовая, чёрная, M               | 1.2 л | Денмарс            |
| WB-10293           | Набор контейнеров для хранения, 3 шт.     | 3.8 л | Северный склад     |
```

`OLD/ART-402` is absent here even when its name or SKU would otherwise match a query. There is no reset button: returning to the default view means clearing the search directly and selecting `Актуальные товары`.

### Wide desktop: explicit archive inspection with long values

```text
[ контейнер ] [ Показывать: Все товары, включая архив v ]  Найдено: 2

| SKU                | Название                                  | Объём | Селлер             |
| OLD/WB-10293       | [Архив] Набор контейнеров для хранения... | 3.8 л | Северный склад...  |
| WB-10293           | Набор контейнеров для хранения, 3 шт.     | 3.8 л | Северный склад     |
```

Hovering the truncated name or seller exposes the full value. Hovering `Архив` exposes the archive warning. There is no coloured row background.

### Narrow viewport: default current catalog

```text
Товары (SKU)

[ Название, SKU, селлер или артикул WB ]
[ Показывать: Актуальные товары v ]
Найдено: 248

< horizontal scroll inside table >
| SKU                | Название ...             | Объём | Селлер ... |
| WB-10293           | Набор контейнеров...     | 3.8 л | Северн...  |
```

No `OLD/` row is visible in this default state, including when its name or SKU would otherwise match the search. Only the table scrolls horizontally; no column is dropped.

### Narrow viewport: explicit archive inspection

```text
Товары (SKU)

[ контейнер ]
[ Показывать: Все товары, включая архив v ]
Найдено: 2

< horizontal scroll inside table >
| SKU                | Название ...             | Объём | Селлер ... |
| OLD/WB-10293       | [Архив] Набор контей...  | 3.8 л | Северн...  |
| WB-10293           | Набор контейнеров...     | 3.8 л | Северн...  |
```

The archived row is visible only after the operator explicitly selects `Все товары, включая архив` (or `Только архивные товары`). The filter placement remains identical to wide view; no archive cue depends on row colour.

## Required states

| State | Exact visible outcome |
| --- | --- |
| Loading | The filter zone stays in place. The table body shows `TableSkeletonBody` with four columns; no empty message appears underneath it. |
| Current catalog is truly empty | With empty query and `Актуальные товары`: `Нет актуальных товаров` and hint `Создайте SKU или выберите «Все товары, включая архив», чтобы проверить историю.` |
| Query matches only hidden archives | With `Актуальные товары`: `Среди актуальных товаров ничего не найдено` and hint `Измените запрос или выберите «Все товары, включая архив», чтобы проверить архивные карточки.` |
| Explicit archive mode has no result | With `Только архивные товары`: `Архивных товаров не найдено` and hint `Измените запрос или вернитесь к актуальным товарам.` With `Все товары, включая архив`, the ordinary query-empty wording is `По этому запросу товаров нет`. |
| Catalog/search failure | `ErrorNotice`: `Не удалось загрузить каталог. Обновите страницу и повторите поиск.` Existing successful rows are not falsely labelled as a complete result. |
| Long data | Fixed widths, ellipsis plus full-value tooltips and table-local horizontal scroll as specified above. |
| Narrow viewport | Vertical filter stack above the same four-column scrollable table; controls and result counter remain visible and do not overlap. |
| Forbidden / partial / repeat / cancel | Not applicable: this stage adds no mutation, privilege-dependent action, batch processing or cancellable operation. Opening the archive is a reversible local filter choice. |

## Truthful UI-kit zone mapping

| Zone | Existing UI-kit component and actual use | Deliberately not used |
| --- | --- | --- |
| Touched filter zone above the catalog table | `FilterBar` provides the outlined, responsive filter surface and its built-in `TextField` renders only `searchPlaceholder="Название, SKU, селлер или артикул WB"`; it has no label/aria-label API, so no separate visible `Поиск` label is in scope. `SelectField` renders labelled `Показывать` from a controlled string value and named options. There is no `Сбросить` action: direct text clearing plus the selector are the complete, mapped controls in this task. | `PrimaryAction`, `SecondaryAction`, `IconAction`, `CheckboxField` and `TabsBar`: none is required for the archive filter, and introducing an action solely for reset would add an unrelated control. |
| Touched archive indication in the existing table | `StatusChip` with `tone="neutral"`, label `Архив` and a hint. `TextCell` behaviour (ellipsis plus tooltip) is the required text treatment for long name/seller values. | `MarkChip`: it expresses a product attribute such as ЧЗ, not archived history. |
| Touched table states | `TableSkeletonBody` for loading, `EmptyState` for concrete empty states, `ErrorNotice` for catalog failure. | `ModalDialog`, `ActionMenu`, `PrintAction`, `ScannerLine`, quantity/plan cells and dangerous actions: no task requirement creates a zone for them. |
| Existing legacy S-01 shell, detail panel and create form | Preserved, not migrated by this task. The S18 change may introduce only the components above into the touched filter/table zones. | `ScreenShell`, `ScreenHeader`, `ToolbarLine`, `DataTable`: migrating the complete legacy screen or replacing its row-selection behaviour is outside BLG-D06. |

All named components are exported by `frontend/src/ui-kit/index.ts`. The selected components cover the proposed zones; no local component, custom chip or colour is authorised.

## Out of scope

- Dev implementation, API/data migration, archive-marker rewrite, external marketplace operations, deploy and live-browser approval.
- Hiding or changing archive treatment in FF/seller product pickers, seller stock screens or any other surface listed as unchanged above.
- Creating products, changing product selection semantics, row actions, permissions, scans, print behaviour or pagination.

## S09 verdict

`UX_CONTRACT_READY`: this revised, task-specific UX contract supplies the surface boundary, filter semantics, archive identification, state mockups, narrow/long-data handling and actual UI-kit mapping required for independent S10 re-review.
