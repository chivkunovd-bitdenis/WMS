# S10 DESIGN_REVIEW - BLG-D06

Role: `pipeline-product`
Reviewer: `codex-pipeline-product-blg-d06-s10-rereview2`
Reviewed input: `tasks/BLG-D06/S09-UX-CONTRACT.md`
Canon: `docs/product/UX_CANON_RU.md`
Verdict: `DESIGN_APPROVED`

## Decision

The current S09 contract is approved for the catalog-only archive-filter change.
It gives the operator a safe default in which `OLD/` products are absent, while
keeping archive history reachable only through an explicit `SelectField` choice.
The visible archive cue, table behavior, states, long-data handling and narrow
layout are concrete enough for case derivation and later implementation review.

This approval is limited to the `S-01` catalog filter/table zones named in S09.
It does not approve changes to product pickers, seller stock, detail/create
zones, API/data contracts, external operations or any other screen.

## Re-review findings

| Finding | Result | Evidence in current S09 |
| --- | --- | --- |
| `DR-R1` narrow default exposed an archived row | Closed | The narrow default mockup selects `Актуальные товары` and shows only `WB-10293`; it explicitly states that no `OLD/` row is visible. A separate narrow mockup selects `Все товары, включая архив` before showing `OLD/WB-10293`. Desktop and narrow semantics now agree. |
| `DR-R2` filter controls were not truthfully mapped to ui-kit | Closed | Search is now explicitly placeholder-only through `FilterBar.searchPlaceholder`; S09 makes no unsupported visible-label or accessibility-name promise. The separate `Сбросить` action was removed from scope. Reset behavior is expressed through direct query clearing and selecting `Актуальные товары`. The archive control maps to the existing labelled `SelectField`. |

## Canon and component check

- The filter zone remains above the table through `FilterBar`, matching R-03.
- The archive selector is one exact, labelled `SelectField` with concrete values,
  default behavior and AND semantics with search.
- Revealed archives keep the literal `OLD/` SKU and add one neutral
  `StatusChip` with an exact label and hint; no row fill or local color meaning is
  introduced, matching R-11, R-14 and R-16.
- Loading, empty and failure states map to exported `TableSkeletonBody`,
  `EmptyState` and `ErrorNotice`, matching R-21 through R-23.
- Long values have fixed widths, ellipsis plus full-value tooltips, while narrow
  layouts stack controls and keep all four columns in a table-local horizontal
  scroll. No identifier column is dropped.
- The proposed visible elements are exported from `frontend/src/ui-kit/index.ts`;
  the contract does not require a new local component or a ui-kit modification.

## Product safety conclusion

The approved design directly addresses the warehouse risk: archived cards are
not present in ordinary catalog work, and an operator must make an explicit,
visible filter choice before they can inspect one. Once revealed, an archive is
identified by both its existing `OLD/` SKU and the neutral `Архив` chip, so the
history path does not make an old card look current.

No S11/S12/Dev work, runtime code, pipeline file, deploy, production system,
WB/Ozon operation, credential or secret was changed by this review.
