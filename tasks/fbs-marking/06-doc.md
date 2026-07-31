# 06 — Док

## Бизнес
В заказ FBS можно внести КИЗ/УИН/IMEI/GTIN в WB и видеть статус проверки; КИЗ связывается с уже существующим кодом в модуле Честный Знак.

## Технически
API `/operations/fbs-orders/{id}/markings`; WB meta PUT/GET; lookup `MarkingCode.cis_code` без создания новых кодов.

## Follow-up
FOR UPDATE + IntegrityError recovery; bg sync job; format validation; Playwright.
