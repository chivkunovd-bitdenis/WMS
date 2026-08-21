# S12 TASK_CUT - BLG-D06

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

**Card ID:** `BLG-D06-C1`
**Title:** Keep `OLD/` catalog products out of the ordinary `S-01` list and
search by default, while making their history available only through an
explicit archive scope.

This is one atomic vertical card. The observable warehouse outcome requires
the same scope to govern the initial list, text search, visible counter,
selection and every empty state. Separating a selector from local result
filtering would allow an exact archive search to leak an old card into routine
work; separating the table treatment from the scope would make an explicitly
opened archive indistinguishable from current stock. The card is complete only
when a routine operator sees current products only and deliberately changes
`Показывать` before an `OLD/` record can appear.

## Card contract

### Archive classifier and result rule

`sku_code` starting with the exact, case-sensitive literal `OLD/` is the sole
archive classifier. Product name, seller, sort order, WB vendor code, barcode,
similarity to another SKU and any lifecycle field must not classify a row.

`ProductsScreen` keeps a local `archiveScope` with these exact values:

| Value | Operator label | Visible rows |
| --- | --- | --- |
| `active` | `Актуальные товары` | Rows whose `sku_code` does not start with `OLD/`. |
| `all` | `Все товары, включая архив` | All already loaded rows. |
| `archived` | `Только архивные товары` | Only rows whose `sku_code` starts with `OLD/`. |

`active` and an empty text query are the only first-open, route-return and
reload state. The scope is not persisted in URL, history or storage. Text
search remains a case-insensitive substring match over the existing name, SKU,
seller and WB vendor-code fields; it is combined with archive scope using
logical AND. The ordering of current rows remains the existing ordering.

The result counter, table rows, empty state and selected row all derive from
that one post-scope, post-query result. An exact or partial match existing only
in an archive does not override `active`. When a query or scope change hides a
selected row, selection is cleared before the detail panel can describe a
hidden product.

### Visible S-01 result

The card changes only `/app/catalog/products` (`S-01`) in the existing
`ProductsScreen` search/filter line and four-column table.

- Add one labelled `SelectField` named `Показывать` beside the existing search
  control. It exposes exactly the three labels and values above; there is no
  archive tab, reset button, modal, row action or automatic selection.
- Keep the existing columns and their order: `SKU`, `Название`, `Объём`,
  `Селлер`. A visible archive row retains its literal `OLD/` SKU and has one
  neutral `StatusChip` labelled `Архив`, with hint
  `Архивная карточка: не выбирайте для текущей работы без проверки истории.`
  There is no archive row fill or new colour meaning.
- Use the approved ui-kit components only in the touched zones: `FilterBar`,
  `SelectField`, `StatusChip`, `TextCell`, `TableSkeletonBody`, `EmptyState`
  and `ErrorNotice`. The legacy screen shell, creation form and detail panel
  remain in place except for clearing a selection that is no longer visible.
- Preserve S09 long-data and narrow-layout rules: fixed SKU/name/volume/seller
  columns, tooltips for truncated text, an archive cue beside a truncated name,
  stacked filters on narrow viewports and table-local horizontal scrolling.

Loading remains a four-column skeleton. The implementation must render the
approved state messages rather than an unqualified empty list:

| Condition | Required visible message |
| --- | --- |
| Empty active catalog with an empty query | `Нет актуальных товаров` |
| Query has archive-only matches while scope is `active` | `Среди актуальных товаров ничего не найдено` |
| Empty `archived` scope | `Архивных товаров не найдено` |
| Empty query result in `all` scope | `По этому запросу товаров нет` |
| Catalog load/search failure | `Не удалось загрузить каталог. Обновите страницу и повторите поиск.` |

### Data, API and query boundary

The existing application fetch remains authoritative: `App.tsx` reads
`GET /products` and enriches those rows from the existing `GET
/products/ff-catalog` read. `BLG-D06-C1` introduces no endpoint, request
parameter, response field, pagination rule, authorization rule, cache policy,
server-side query, database read/write, migration, backfill, worker, queue or
external marketplace request.

The archive scope is a presentation filter applied to the already loaded
`ProductRow[]` before the current local text search and before all visible
derived state. It neither mutates `products` nor changes the payload received
from either existing endpoint. A load failure must show the approved failure
state; it must not fall back to an unfiltered previous result and thereby
surface an archive.

No product is deleted, renamed, merged, restored, relinked, selected,
authorized differently or written as a consequence of selecting an archive
scope. Tenant, seller, stock, reservation, marking-code, print and audit
records stay unchanged.

## Implementation surface and ownership

| Surface | File(s) | Bounded responsibility |
| --- | --- | --- |
| S-01 archive scope, combined local query, counter, row visibility, selection clearing and approved states | `frontend/src/screens/v2/ProductsScreen.tsx` | Add the controlled scope and derive all list state from it; preserve adjacent detail/create behaviour. |
| Existing catalog read boundary | `frontend/src/App.tsx` | No intended logic change. It remains the owner of the existing `/products` and `/products/ff-catalog` reads; any proposed API/query change is out of scope and requires S12 rework. |
| Existing UI kit | `frontend/src/ui-kit/index.ts` and named exported components | Consume existing exports only. No ui-kit extension or custom archive component is authorized. |
| Direct browser regression proof | `frontend/tests-e2e/catalog-products-archive.spec.ts` (new) | Seed only isolated local fixtures and assert the S-01 route's visible contract; no live marketplace or production traffic. |

No product picker, FF catalog, seller stock screen, product detail, product
creation, backend route, service, model, migration, worker, external client or
deployment file belongs to this card.

## Required executable cases for S15

S15 must turn every row below into a direct case plus independent destructive
coverage before S16 Product-before-Dev can approve this card.

| ID | Fixture / action | Required observable result |
| --- | --- | --- |
| `D06-C1-01` | Current and `OLD/` sibling products; first open, route return and reload | `active` is selected, the count and rows exclude every `OLD/` SKU, and no archive scope is restored. |
| `D06-C1-02` | Exact and partial text matches that exist only in archived SKU, name, seller and WB vendor code | In `active`, none appears and the archive-only empty message is shown; matching current rows remain visible when present. |
| `D06-C1-03` | Current/archive siblings; explicitly choose `all`, then `archived`, then `active` | `all` shows both and `archived` only `OLD/` rows, each revealed archive has its literal SKU and neutral chip; returning to `active` hides it again. |
| `D06-C1-04` | Each scope with text queries, clearing text, and a selected archive row made hidden | Query and scope use AND; clearing text preserves scope; hiding the selected archive clears the detail selection. |
| `D06-C1-05` | Active catalog empty, archive-only search match, archived scope empty, ordinary all-scope query empty, loading and failed catalog read | Each condition shows the exact approved state and failure never presents a previous/unfiltered result as complete. |
| `D06-C1-06` | Long SKU/name/seller values and `360 x 640 CSS px` viewport | Archive chip remains visible, full text is accessible by tooltip, filters stack, all four identifiers remain in the horizontally scrollable table, and nothing overlaps. |
| `D06-C1-07` | Instrument existing reads while switching scope and searching | No added API parameter, endpoint, write, mutation, product merge, external WB/Ozon call or data change occurs; only local visible result state changes. |
| `D06-C1-08` | Values containing `old/`, `OLD`, or similar text outside the initial exact `OLD/` SKU prefix | They remain current; only the exact case-sensitive SKU prefix classifies an archive. |

S19 must bind the accepted S15 cases to an isolated Playwright/local-stack
driver and a deterministic reset. S20 must reject a solution that filters only
the initial list but not search/count/selection, persists archive mode,
classifies by non-SKU text, changes the API contract, leaves a hidden selection
active, replaces an error with old unfiltered data, or spreads the rule into a
picker or seller surface. S24 and S25 independently verify the visible default,
explicit archive inspection, reset, reload, empty/failure, long-data and
narrow-layout journey on the accepted artifact.

## Dev and review boundaries

S18 may implement only `BLG-D06-C1`, and only after a separate S15 case writer
and independent case auditor supply the complete coverage matrix and a separate
S16 Product actor approves the exact card package. It must not add a backend
filter, persist user preference, alter data, include another catalog/picker,
invoke WB/Ozon, deploy, or access credentials.

Any change to the archive classifier, S-01 surface list, API/query boundary,
or one-card atomic boundary invalidates this cut and returns to S12 before a
new S16 approval.

## Explicit exclusions

This S12 stage creates no implementation, test execution, commit, push,
deployment, release, production action, live-browser acceptance, external
marketplace operation, secret access, data change, API change or controller
change. It does not advance S15, S16, S17 or S18.

## Handoff

**Next stage:** `S15 CASE_FACTORY`, owned by a separate `pipeline-ba` case
writer; an independent `case-breaker` and `case-auditor` must challenge and
accept its coverage. This S12 author does not author, audit or approve that
case package.

## Verdict

`TASK_CUT_READY`: `BLG-D06-C1` is the smallest user-observable implementation
card that keeps historical `OLD/` catalog products out of routine work while
preserving deliberate, unambiguous archive inspection and the existing data/API
boundary.
