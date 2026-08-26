# Кейсы волны 2А

## Позитивные

1. Завершённая приёмка создаёт один `inbound_completed` с фактическими lines, SKU/названием,
   селлером, документом, складом, автором и physical item quantity.
2. Возврат создаёт отдельный `return_completed`, не маскируется приёмкой и сохраняет автора.
3. FBS WB: подбор → undo → новый подбор создаёт `fbs_pick`, reversal и новый `fbs_pick`; повтор
   HTTP/idempotency-key каждого шага не добавляет строк.
4. FBS Ozon проходит тот же сценарий через фактический `FbsOrderProductPick`, включая отмену и
   повтор, без требования WB-only event.
5. Упаковочный event создаёт факт операции и линии, но не меняет существующую ставку/сумму
   `staff_packaging_billing_service` и не создаёт employee money entry.
6. Зафиксированное хранение создаёт один факт только от fixed storage statement/measurement; черновой
   statement его не создаёт.
7. Завершённая отгрузка создаёт факт с документом/линиями; возвращающий отменяющий переход создаёт
   reversal, не переписывая исходник.
8. Recovery для явного tenant и периода находит пропущенные факты, создаёт их один раз, сообщает
   `found/created/already_present/conflicted`, а второй запуск даёт `created=0`.
9. Recovery воспроизводит автора из durable source для inbound, Ozon pick и unload; source rows
   до cutover не backfill-ятся и не получают выдуманного автора или `source`.

## Негативные

1. User-source без автора, system-source с автором, пустой operation code, отрицательное физическое
   количество там, где оно невозможно, и cross-tenant FK отклоняются.
2. Один idempotency key с другой source tuple/operation не создаёт новый факт и возвращает понятный
   конфликт.
3. Повтор того же canonical source tuple не удваивает факт; попытка второго reversal исходного
   факта не меняет историю.
4. Recovery не читает `DocumentEvent`, не создаёт строку по отсутствующему/неподтверждённому
   документу, не захватывает чужой tenant и не превращает старый ledger в факт.
5. Ошибка recovery не удаляет уже созданные факты и не меняет складской документ, ledger, тариф или
   упаковочную выплату.
6. Shipped unload после первого `cancel_request` остаётся `STATUS_SHIPPED`; повтор того же cancel
   возвращает ровно тот же `marketplace_outbound_reversal` по source tuple и не перезаписывает
   `cancelled_by_user_id`, даже если retry пришёл с другим performer.

## Регрессия и граница cutover

1. Существующие приёмка, возврат, FBS, упаковка, отгрузка и фиксирование хранения завершаются как
   раньше; `DocumentEvent` продолжает best-effort поведение и не становится обязательным.
2. `uq_billing_ledger_source_event`, legacy invoices, legacy ledger, месячные storage ledger строки
   и `staff_packaging_billing_service` остаются без схемных/поведенческих изменений.
3. Перед cutover read-model оставляет legacy entry legacy; после cutover принимает только новый
   факт; одна операция на границе не теряется и не показана дважды.
4. Параллельные retry/recovery одного источника сохраняют одну запись на PostgreSQL.

## PostgreSQL evidence

На PostgreSQL применить миграцию с `20260825_0109`, подтвердить ровно один Alembic head, FK,
partial unique idempotency, source uniqueness и report indexes. Зафиксировать команду, exit code,
inspection и выборку сценария WB/Ozon retry/recovery в
`docs/evidence/billing-02a-operation-facts/OPERATION-FACTS-PROOF.md`.

## Browser

Не применяется: 2А не меняет экран, route или видимый API. Нельзя заменять это формальным
Playwright/скриншотом. Живой браузер обязателен в волнах с экраном, начиная с seller-report, а здесь
доказательство — серверные тесты, PostgreSQL и независимый review.
