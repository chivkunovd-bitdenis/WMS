# B05 sanitized state/network log

## Boundary

Лог намеренно не содержит credentials, cookie, token, request/response bodies или секретных заголовков. Фиксируются только видимые пользователю transitions и безопасные агрегаты.

## Environment recovery

- Предыдущие Browser tabs были закрыты пользователем.
- По прямому разрешению открыта новая in-app Browser tab на Railway staging.
- Existing FF-admin session сохранилась; повторный credential entry не понадобился.
- Route восстановлен `/app/ff/products`; A/B state совпал с B04.
- Verdict: environment event, не application defect.

## Read-only state

- Catalog initial: 212 rows; exact seller filter: 2 rows.
- Product A: total3, sorting0, cells3, available3.
- Product B: total2, sorting0, cells2, available2.
- Warehouses/cells read-only: exact FBS warehouse + foreign `Тестовый`; foreign state не изменялся.
- Movements: initial/reload visible empty; после manual refresh — 80 recent rows.
- Background movement digest: один safe read-only run; status `done`; visible result `Всего движений: 132`.

## Mutation boundary

- Catalog mutation: none.
- Cell create/edit/delete/physical print: none.
- Transfer submit: none.
- Inventory/count/adjustment: none; feature placeholder.
- WB/external/shared/foreign mutation: none.
- Final reload read-back: A3/B2, sorting0, cells/available3/2.

## Runtime and files

- Standard runtime: 1280×720 DPR1; exported PNG 1280×720.
- Wide runtime: 1920×1080 DPR1; exported PNG 1873×1080 due IAB limitation.
- PNG saved: 54; personally viewed: 54; application code changed: no.
