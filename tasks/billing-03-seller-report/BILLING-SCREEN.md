# Экранный контракт Wave 3: `/app/ff/billing`

`/app/ff/billing` has no entry in `frontend/screens.registry.json`; it is
explicitly the billing exception, not S-19/S-31. Wave 3 changes only the
existing charges zone into the **«Селлеры»** report. The existing route, shell,
header rhythm and legacy invoice zone stay in place.

At 1600px: `ScreenHeader`; one outlined filter `Paper`; one outlined compact
summary `DataTable`; and, after a seller selection, a separate outlined detail
block. Summary fixed columns are Seller, Operations, Items, Not billable,
Show operations; finance-on adds Unpriced and Accrued. Up to four existing
metric-strip values sit above it. Detail uses fixed columns Date/time,
Document/source, Service, Product/SKU, Physical quantity, Result, Open source;
finance-on adds Unit, Rate and Amount. Numbers align right. No fully coloured
rows, custom tab/filter/dropdown/button/table or nested decorative card.

The seller period uses shared generic Moscow date-range control plus today,
7 days, 30 days, current month and previous month. It cannot end after current
Moscow calendar day; server validation remains authoritative and UI displays an
inline error. Finance is a local preference keyed by tenant/user/sellers tab.
Finance-off has no monetary UI/API data, `billing_ledger_entry_id` or
invoice-history column. Finance-on is still view-only: «Счёт выставлялся» shows
`—` for exact known 0, `✓ 1`/`✓ N` for exact known positive count and
tooltip-explained «Нет данных о старом счёте» for unknown. It has neither
select checkbox nor «Выставить счёт», so repeated issuance remains neither
blocked nor performed. Invoice selection, V2 source, preview/print and
Invoice-tab changes belong solely to Wave 4; Employees belongs to Wave 5.

Detail's first load inserts precisely one storage row for that seller/interval:
period, litres-days, status and finance-on amount. It has no direct open action
and never expands into products/days/warehouses. Missing dimensions explain the
problem. Subsequent cursor pages append only operation rows. Loading is table
skeleton, network errors are `ErrorNotice`, empty states explain the next
operator action, disabled/missing source actions explain why. Screenshot and
live-browser acceptance cover both finance modes, normal/error/empty and this
single storage-row invariant.

Статус экранного файла до реализации: `CONTRACT_ONLY`, не verdict готового UI.
Итоговый `VERDICT.md` создаётся только после отдельного ui-critic и живого
browser judge; он не может объявить принятыми legacy «Счета», Wave 4 invoice
flow или Wave 5 employees, потому что они не затрагиваются.
