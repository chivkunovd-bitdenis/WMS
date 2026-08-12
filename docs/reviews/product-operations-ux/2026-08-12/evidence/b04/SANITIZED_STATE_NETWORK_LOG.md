# B04 sanitized state and transition log

Этот журнал содержит только безопасные business identifiers и итоговые read-back. Credentials, cookies, headers, tokens, raw response bodies и внешние WB-вызовы не сохранялись и не использовались.

## Exact fixture

- Request ID: `41823675-2b08-4714-97b6-8782486c4dda`.
- Human number: `000007`.
- Seller: `B01 UX Seller 960724`.
- Products: synthetic A accepted `3`, synthetic B accepted `2`.
- Boxes: `0` в handoff B03; sorting source visually `Россыпь`.
- Exact warehouse inferred and visually cross-proved: `FBS WB 1155120`, code `fbs-wb-53692f4a-1155120`.
- Exact storage cell: `A 1.1`, barcode `LOC-36F984B31C3D`.
- System location `Сортировка` не использована как destination.
- Warehouse `Тестовый` и его synthetic cells не использовались.

## Fixture drift

В connected staging tenant не найдено warehouse с названием `Review Warehouse`. Exact request destination dropdown содержит только `A 1.1`; в exact warehouse второй storage cell нет. Поэтому two-cell split получил `BLOCKED_FIXTURE`, а финальная one-cell раскладка выполнена только в exact A 1.1.

## Baseline read-back

| State | A | B | Evidence |
|---|---:|---:|---|
| Document status | sorting | sorting | `b04-001`, `b04-005` |
| Sorting remaining | 3 | 2 | `b04-005` |
| FF total | 3 | 2 | `b04-009`–`b04-012` |
| FF Sorting | 3 | 2 | `b04-010`, `b04-011` |
| FF cells | 0 | 0 | `b04-010`, `b04-011` |
| FF available | 0 | 0 | `b04-010`, `b04-011` |

## Draft validation transitions

- Positive qty without cell: UI draft summary became1; Save silently removed incomplete row; stock unchanged.
- Zero with valid cell: Save silently removed row; stock unchanged.
- Decimal1.9 with valid cell: UI and durable draft became1 without warning.
- Overage4: client controls disabled; no stock movement.
- Negative -1: visible in number control without inline error; server Save of negative was not performed and is not claimed.
- Valid draft A1.1=1: Save durable; reload/reopen restored1; FF stock stayed Sorting3/2.
- Save double-click: one visible durable draft, no duplicate row.

## Recovery transitions

- Dirty saved1→unsaved2 + Close: no warning; reopen restored saved1.
- Dirty draft + Back/Forward: dialog visually persisted while runtime route changed; unsaved value lost.
- Dirty draft + reload: no warning; document closed to queue; reopen required exact row search.
- Add-cell double-click: one additional blank row visible; remove returned to one saved row.

## Partial apply

- Applied: A=`1` → exact A 1.1.
- Double-click result: one visible transition only.
- Document read-back: total remaining=`4`, A distributed=`1`.
- Queue reload: exact row remaining=`4`.
- Stock read-back:
  - A total3, Sorting2, cells1, available1.
  - B total2, Sorting2, cells0, available0.

## Final apply

- Remaining draft: A=`2`, B=`2`, both exact A 1.1; earlier A=`1` remained visible as posted distribution.
- Final double-click Apply: one terminal transition, remaining0, status visually `Оприходовано`; repeat Apply control absent.
- Sorting queue after Close and after reload: exact seller/document absent.
- Dashboard after reload: №000007, A3/B2, status `Оприходовано`.
- Final stock:
  - A total3, Sorting0, cells3, available3.
  - B total2, Sorting0, cells2, available2.
- Conservation: baseline total5 = final total5; delta Sorting −5, delta cells +5, delta available +5.
- Cell directory limitation: A 1.1 exists, but no per-cell SKU/qty read-back is exposed in available UI.

## Boundary

- Only isolated synthetic request and existing synthetic warehouses/cells were touched.
- No external WB action, credential/secret page, shared tenant or seller mutation.
- No application code change.
- B05 not started.
