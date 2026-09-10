# WMS-429 root manual UI evidence — 11 September 2026

Environment: local frontend http://127.0.0.1:5429, API http://127.0.0.1:8429, isolated PostgreSQL wms429_ui_20260911. Dummy account warehouse-wms429@example.com. No production document, marketplace shipment, or stock publication was changed. This is not evidence of deployed production behavior.

## Catalog publication filter — actual clicks

Opened Catalog, expanded Передача остатков, selected Включена на Ozon. The table displayed exactly the two Ozon-enabled fixture products out of three. Selected both rows and opened Задать остаток ·2. The existing mass-edit form displayed WB/Ozon publication checkboxes and Остаток по штукам; switching the latter exposed numeric publication ceilings per warehouse. External-account notices are expected in this intentionally account-free fixture. Closed without saving or publishing stocks.

With the publication filter still selected, entered WMS429-OZ-A in search. The result became one row, Ozon productA, and previous selection was cleared. This confirms actual composition with search and selection reset, not a claim about a real marketplace write.

## Ozon overdue worklist — actual clicks

Opened FBS->Новые: the deliberately yesterday-deadline Ozon posting appeared. Clicked Просрочены: empty list, no Ozon posting. This directly confirms worklist exclusion. The deadline tooltip still said WB and a multi-position Ozon compatibility product rendered unmapped; these observed defects were sent to the Ozon owner for correction, and this is not their acceptance.

## Pending final UI pass

After the final API reload, inspect Ozon position identities, packing/box labels and final confirmation; do not execute final delivery or marketplace calls. Inspect the final storage report and save final evidence here. No claim of physical TSD/printer acceptance.

## Final integration UI pass (root)

With Ozon barcode fixtures deliberately different from Product WB barcodes, actual worklist showed both Ozon names/offers/SKUs and the correct Ozon barcodes. Deadline tooltip now says Ozon. Active supply row shows Ozon, Ozon warehouse, 1 order / 3 units, and “Этикетки коробов”; WB row remains WB/QR. Navigation from incomplete picking to packing/boxes is accessible. Final delivery dialog explicitly says Ozon carriage will be created/confirmed; cancelled without submitting.

Actual start-work returned200, but card reread returned500 because nullable wb_supply_id failed FbsSupplyOut validation. Fixed in6e65feda; UI reread after reload remains pending.

Storage existing menu /app/ff/inventory now opens the simple report; no extra sidebar route. Fixture total6 liter-days/900kopecks. Seller expansion shows volume2/1, liter-days4/2, period rate150kopecks, current rate200, amount600/300. CategoryA reduces total to4/600; date09September plus categoryA yields2/400. These are actual UI interactions against isolated data, not production accounting verification.
