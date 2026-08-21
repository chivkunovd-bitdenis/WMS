# S11 PRODUCT_CONTRACT_APPROVAL - BLG-D06

## Product decision

Product approves an archive-safe catalog experience for `S-01`, route
`/app/catalog/products`. Ordinary catalog work must begin with current products
only. A product is archived when its existing `sku_code` begins with the
literal prefix `OLD/`; this task does not introduce another archive status or
change that marker.

The business outcome is that an operator cannot mistake a historical card for
the current product merely because the archived card sorts first or matches a
search more closely. Archived cards remain available for deliberate historical
inspection through one explicit archive filter. They are not deleted, renamed,
merged, or silently made current.

This approval is limited to the catalog search/filter line and four-column
product list approved by S09 and S10. Product pickers, seller stock lists,
product details, SKU creation, packing, scanning, printing, and marketplace
flows retain their existing contracts. Expanding archive suppression to one of
those surfaces requires a separately classified contract and its own cases.

## Approved operator journey

1. When the operator first opens `S-01`, returns to the route, or reloads the
   browser, the archive filter is `Актуальные товары` and the text search is
   empty. The filter choice is not persisted.
2. The visible table and `Найдено: N` counter are calculated from the same
   result set after both archive scope and text search have been applied.
3. In `Актуальные товары`, every row whose SKU starts with `OLD/` is excluded
   before the result is shown. An exact query for an archived SKU or an exact
   match on its name, seller, or WB vendor code must not make that archived row
   appear.
4. The operator may deliberately choose `Все товары, включая архив` to inspect
   current and archived cards together, or `Только архивные товары` to inspect
   archive history only. Changing the filter reveals rows but never selects,
   edits, restores, or otherwise acts on a product.
5. Every revealed archived row keeps its literal `OLD/` SKU and also shows the
   neutral `Архив` status chip with the approved warning hint. The operator can
   therefore distinguish history even when the name is long or resembles a
   current card.
6. Text search and archive scope combine with logical AND. Clearing search does
   not change archive scope; returning to ordinary work requires selecting
   `Актуальные товары`.
7. If a selected row becomes hidden after either control changes, the selection
   is cleared. A hidden archived card must not remain as stale active context
   for an adjacent detail or action.
8. A reload or a later return to the route restores the safe current-only
   default. Browser history must not silently reopen an archive view as the
   ordinary initial state.

## Warehouse rationale for visible elements

- The `Показывать` selector makes archive access deliberate and predictable in
  the standard filter zone. It preserves historical access without mixing old
  cards into routine catalog work.
- The exact options `Актуальные товары`, `Все товары, включая архив`, and
  `Только архивные товары` state the result set in warehouse language instead
  of exposing an implementation flag.
- The literal `OLD/` identifier preserves the existing audit clue. The neutral
  `Архив` chip makes the same fact scannable and prevents a long product name
  from hiding the warning.
- `Найдено: N` counts only the visible filtered result, so the operator can
  trust the number as the size of the work list currently on screen. It must
  not imply that hidden archive rows are actionable.
- Specific empty and error states explain whether the current catalog is empty,
  the query matched no current product, or loading failed. They avoid making a
  hidden archive match look like a missing or deleted product.

## UI layer

- The changed surface is only `ProductsScreen` on `S-01`, in the existing
  filter zone and product table.
- The existing search uses placeholder
  `Название, SKU, селлер или артикул WB`. The new labelled `SelectField` is
  `Показывать` with values `active`, `all`, and `archived` represented by the
  exact labels approved above.
- `active` is the only default. `all` and `archived` require an explicit current
  operator choice and are not persisted.
- Revealed archive rows use the existing `StatusChip` with label `Архив`,
  neutral tone, and hint
  `Архивная карточка: не выбирайте для текущей работы без проверки истории.`
  There is no archive row fill, new status colour, action, modal, or tab.
- The table keeps columns `SKU`, `Название`, `Объём`, `Селлер` in that order.
  Long values use ellipsis and full-value tooltips. The archive chip remains
  visible beside a truncated name.
- On narrow viewports, search and archive controls stack above the table. The
  four-column table scrolls horizontally in its own container; identifiers are
  not dropped or wrapped into ambiguous cards.
- Loading uses the approved four-column table skeleton. Empty and failure
  messages are exactly those specified in S09. Existing successful rows must
  never be presented as a complete result after a catalog/search failure.

## API layer

No API endpoint, request, response, pagination, authorization, or external
contract changes under BLG-D06. The existing catalog read may continue to
return current and `OLD/` records. The approved `S-01` presentation applies the
archive scope to that existing response before displaying the ordinary list and
counter.

The existing case-insensitive substring search remains over product name, SKU,
seller, and WB vendor code. Archive scope is an additional local result rule,
not a new server query contract. This stage authorizes no live WB/Ozon call and
no marketplace-side search or mutation.

## Data layer

- No schema, migration, backfill, worker, queue, database write, or product
  lifecycle transition is introduced.
- The existing literal SKU prefix `OLD/` is the only archive classifier for
  this card. Product name, seller, sort order, synchronization time, or
  similarity to another SKU cannot classify or unclassify a row.
- Filtering does not delete, rewrite, merge, restore, or relink a product. It
  changes only which existing rows are visible in the approved catalog view.
- Tenant, seller, stock, reservation, marking-code, document, and audit-history
  data remain unchanged. A current and archived card with similar fields remain
  separate records.

## Product invariants and failure handling

- Default catalog search and list results never contain an `OLD/` row.
- An exact archived match does not override the current-only default.
- An archived row can become visible only in `all` or `archived` mode selected
  explicitly by the operator.
- Every visible archived row carries both the literal prefix and neutral archive
  cue; archive meaning never depends on row colour alone.
- Current and archived sibling cards are not deduplicated, merged, or ranked as
  substitutes. In `active`, only the current sibling is eligible to appear; in
  `all`, both may appear with the archive clearly marked.
- The visible result counter, rows, selection, empty state, and error state must
  describe one consistent filtered result set.
- Filtering failure must not fall back to an unfiltered list. If the catalog
  cannot be loaded safely, the approved error state is shown.
- The feature has no write side effect, external call, replay, privilege change,
  or automatic product selection.

## Required downstream test proof

S15 must create direct and independent breaker cases for at least:

- first open, navigation return, and reload using `Актуальные товары` with no
  `OLD/` rows;
- exact and partial search matches that exist only in an archived SKU, name,
  seller, or WB vendor code and remain hidden in the default mode;
- `all` showing current and archived sibling cards together, with correct
  archive chip, hint, literal SKU, and visible counter;
- `archived` showing only `OLD/` rows, and switching back to `active` hiding
  them again;
- logical-AND behavior between every archive mode and text search;
- a selected archived row being cleared when a filter change hides it;
- current-catalog-empty, hidden-archive-only match, archive-empty, ordinary
  query-empty, loading, and catalog/search failure states from S09;
- long SKU, name, and seller values, including tooltip access and a visible
  archive cue;
- wide and narrow viewports with stacked controls, table-local scrolling, no
  overlap, and no dropped identifier column;
- proof that filtering causes no API contract change, write, product merge,
  external marketplace call, or mutation of stock, reservation, marking-code,
  or audit data;
- product records that do not begin with the exact case-sensitive literal
  `OLD/`, ensuring similar text elsewhere does not become an archive classifier.

S19 must bind every accepted case to a runnable reference without changing its
oracle. S24 must compare the implemented filter, archive indication, states,
long-data behavior, and narrow layout with approved S09/S10. S25 must
independently walk the default search, explicit archive inspection, reset to
current-only work, reload, empty, and failure journeys in a visible browser on
the exact accepted artifact. None of those later verdicts is granted by S11.

## Out of scope

No S12 task cut, case creation, implementation, test execution, API or schema
change, product picker change, seller stock change, product merge/deletion,
credential operation, live WB/Ozon call, deploy, release, or production action
is performed or approved at S11.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: `S-01` starts with current products only, ordinary
search cannot surface an archived `OLD/` card, and archive history is available
only through an explicit, reversible filter with an unambiguous archive cue.
