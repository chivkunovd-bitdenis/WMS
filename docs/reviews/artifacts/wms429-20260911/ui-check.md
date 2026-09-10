# WMS-429 root manual UI evidence — 11 September 2026

Environment: local frontend http://127.0.0.1:5429, API http://127.0.0.1:8429, isolated PostgreSQL wms429_ui_20260911. Dummy account warehouse-wms429@example.com. No production document, marketplace shipment, or stock publication was changed. This is not evidence of deployed production behavior.

## Catalog publication filter — actual clicks

Opened Catalog, expanded Передача остатков, selected Включена на Ozon. The table displayed exactly the two Ozon-enabled fixture products out of three. Selected both rows and opened Задать остаток ·2. The existing mass-edit form displayed WB/Ozon publication checkboxes and Остаток по штукам; switching the latter exposed numeric publication ceilings per warehouse. External-account notices are expected in this intentionally account-free fixture. Closed without saving or publishing stocks.

With the publication filter still selected, entered WMS429-OZ-A in search. The result became one row, Ozon productA, and previous selection was cleared. This confirms actual composition with search and selection reset, not a claim about a real marketplace write.

## Ozon overdue worklist — actual clicks

Opened FBS->Новые: the deliberately yesterday-deadline Ozon posting appeared. Clicked Просрочены: empty list, no Ozon posting. This directly confirms worklist exclusion. The deadline tooltip still said WB and a multi-position Ozon compatibility product rendered unmapped; these observed defects were sent to the Ozon owner for correction, and this is not their acceptance.

## Pending final UI pass

After the final API reload, inspect Ozon position identities, packing/box labels and final confirmation; do not execute final delivery or marketplace calls. Inspect the final storage report and save final evidence here. No claim of physical TSD/printer acceptance.
