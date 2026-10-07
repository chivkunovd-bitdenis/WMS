# WMS-675 · фактическое восстановление 07.10.2026

Это отдельный production receipt после verified deploy, а не переписывание
исторических bundle или preflight `635ee391`.

## Runtime gate

Host checkout production был `4c532f0cccfb8f99b34d68d9630a3763038fbc5f`.
Контейнер API создан в 06:12:34 UTC из образа, созданного в 06:09:20 UTC.
Буквенный Git SHA в image label, environment и `/app/.git` не записан, поэтому
его нельзя честно выдать за ответ runtime. Вместо догадки проверен весь
исполняемый `backend/app`: 347 Python-файлов контейнера совпали побайтно с
деревом `4c`; SHA-256 обоих манифестов
`bc18cda617ea6a9420d96da263d33f31bdf711f1da2d155f7b214c921487a97a`.
В частности, совпал accepted service observed-handoff
`137e9f7484cd5b4122c43f6ae56a40018dc5b755edc7144aaf48a744a1bafb07`.
Следовательно runtime-код доказанно эквивалентен `4c`; недостаток — отсутствие
в образе собственного, читаемого SHA provenance.

## Что было и что сделано

Новый bounded read подтвердил exact tenant/seller/WMS supply/warehouse и 31
позиций. Ozon ответил на 31 semantic read карточки: 26 положительных и 5
`cancelled`, без unknown, split/weight children либо mismatch состава.

До операции в journal уже находились только 12 observations/targets и ровно
12 completed ledger units. Facts/charges к тому моменту уже были 26/52. Это
не было повторено вслепую: перед commit штатные locks заново увидели 31
observations, 26 cumulative targets, 12 already completed и remaining 14.

Исполнен только принятый путь:

`ozon_targets → make_observation → save_observations →
lock_order_batch_packaging_rows → lock_handoff_batch_products →
conduct_supply → commit`.

Ни ручной delta, ни SQL `UPDATE`, ни seller-wide sync, ни Ozon
ship/approve/deliver/create не вызывались. `save_observations` отдельно
зафиксировал 31 observation; затем один `conduct_supply` commit использовал
cumulative recipe и не мог добавить уже проведённые 12 единиц.

## Независимый результат

Новая read-only session и новый bounded Ozon read дали:

- 26 external positive, 5 cancelled; по всем 31 posting ledger согласован с
  внешней карточкой, расхода на cancelled нет;
- 31 ledger recipe, 26 completed, reversal 0, `missing_delta=0`;
- durable journal содержит 31 observation и target 26, state `confirmed`;
- facts и charges остались ровно 26/52. Их ID-set hashes до этой операции и
  после неё совпадают (`03e300…9722` и `7e3c6e…b2f8`), поэтому этот запуск не
  создал duplicate fact/charge.

## Незакрытый бизнес-пункт

Строгая приёмка восстановления **не завершена**. В обеих фактических таблицах
резервов для scope ноль строк и ноль единиц, то есть свободный stock не
заблокирован. Однако у 14 позиций со статусом `done` сохранён stale
`fbs_order_products.reserved_quantity=1`. Штатный `reserve=False` очищает
это поле только когда находит reservation rows; здесь rows уже отсутствуют и
он законно возвращает управление, не меняя поле. Ручной SQL или новый runner
для «подчистки» этим поручением запрещены.

Итог: **ACCOUNTING_RECOVERED; POSITION_RESERVE_PROJECTION_REMAINING**.
Нужен отдельный минимальный verified code path, который согласует это поле с
нулевыми фактическими reservation rows, после чего — fresh readback. До него
нельзя заявлять полное закрытие WMS-675, хотя повторная accounting delta уже
доказанно ноль.

Полные санитизированные цифры находятся в
[REPAIR_RECEIPT_SANITIZED.json](REPAIR_RECEIPT_SANITIZED.json) и
[INDEPENDENT_READBACK_SANITIZED.json](INDEPENDENT_READBACK_SANITIZED.json).
