# TC-NEW-MP — отгрузка на МП от селлера (каталог для реализации)

Канон для PR: секция `### Test coverage` ссылается на эти ID.

## S — создание и состав (селлер)

### TC-NEW-MP-01 Seller creates MP unload draft without WB warehouse
- **Given:** селлер авторизован, есть склад ФФ, товары с остатком.
- **When:** «Создать отгрузку на МП», не выбирает склад МП, сохраняет черновик.
- **Then:** статус «Черновик»; документ в списке селлера; **не** на дашборде ФФ.
- **Negative:** —

### TC-NEW-MP-02 Seller product table shows SKU, name, available stock
- **Given:** у селлера товар A available=7, товар B другого селлера на складе.
- **When:** открывает форму черновика отгрузки на МП.
- **Then:** в таблице только свои SKU; A показывает «7»; B отсутствует.
- **Negative:** —

### TC-NEW-MP-03 Seller qty exceeds available blocked
- **Given:** available=3 для товара A.
- **When:** указывает 5 к отгрузке и сохраняет/планирует.
- **Then:** ошибка «Недостаточно доступного остатка»; строка не сохраняется / план не выполнен.
- **Negative:** qty=0 не создаёт строку.

### TC-NEW-MP-04 Seller form has no scan/box/pick/ship blocks
- **Given:** селлер, черновик или запланированная заявка.
- **When:** открывает модалку.
- **Then:** нет `ff-mp-boxes`, scan input, «Начать подбор», «Отгружено».
- **Negative:** —

## P — планирование и резерв

### TC-NEW-MP-05 Plan requires WB warehouse and lines
- **Given:** черновик без склада МП или без строк.
- **When:** «Запланировать».
- **Then:** ошибка wb_mp_warehouse_required / no_lines.
- **Negative:** —

### TC-NEW-MP-06 Plan success reserves stock
- **Given:** available=10, в заявке 4 шт.
- **When:** «Запланировать».
- **Then:** статус «Запланировано»; available=6 для других заявок; резерв 4.
- **Negative:** вторая заявка не может зарезервировать >6.

### TC-NEW-MP-07 Draft invisible on FF dashboard; submitted visible
- **Given:** черновик селлера.
- **When:** ФФ открывает дашборд.
- **Then:** черновика нет; после plan — строка в «Запланированные отгрузки на МП».
- **Negative:** —

### TC-NEW-MP-08 Seller cannot edit after plan; unplan works
- **Given:** submitted заявка.
- **When:** селлер меняет qty / seller unplan.
- **Then:** edit → not_editable; unplan → draft, резерв снят.
- **Negative:** —

## F — ФФ подтверждение и сборка

### TC-NEW-MP-09 FF confirms submitted with planned date
- **Given:** submitted заявка.
- **When:** ФФ «Подтвердить» + дата.
- **Then:** статус «Подтверждено»; planned_shipment_date сохранена.
- **Negative:** селлер не может confirm.

### TC-NEW-MP-10 FF creates draft, adds lines manually, no box in draft
- **Given:** ФФ admin.
- **When:** создаёт отгрузку на МП, добавляет строку руками.
- **Then:** короба/скан **не** видны в draft.
- **Negative:** —

### TC-NEW-MP-11 Picking only after confirmed
- **Given:** draft с строками.
- **When:** POST boxes/scan.
- **Then:** 409 not_editable / bad_status.
- **Negative:** —

### TC-NEW-MP-12 Scan +1 and manual qty; limits enforced
- **Given:** confirmed, в заявке 5 шт. товара A.
- **When:** 5 сканов OK; 6-й скан; скан чужого штрихкода; manual > plan.
- **Then:** 6-й → qty_exceeded; чужой → product_not_in_shipment; manual лимит.
- **Negative:** —

### TC-NEW-MP-13 FF edit after confirm marks ff_modified
- **Given:** confirmed.
- **When:** ФФ меняет qty строки.
- **Then:** ff_modified=true в API/UI.
- **Negative:** селлер not_editable.

### TC-NEW-MP-14 Ship deducts stock (regression TC-NEW-MP-01 ship path)
- **Given:** confirmed, scan+pick complete.
- **When:** «Отгружено».
- **Then:** shipped; остаток уменьшен; резерв снят.
- **Negative:** —

## W — склады WB

### TC-NEW-MP-15 Seller reads tenant WB warehouse list
- **Given:** кэш складов заполнен.
- **When:** селлер GET wb-mp-warehouses.
- **Then:** 200, список складов.
- **Negative:** без токена 401.

### TC-NEW-MP-16 Daily sync uses first seller supplies token
- **Given:** два селлера, supplies только у первого (earliest created_at).
- **When:** daily sync task.
- **Then:** tenant cache обновлён; не дублируется per seller.
- **Negative:** нет токена → cache unchanged, warning log.

## R — RBAC

### TC-NEW-MP-17 Seller A cannot see seller B MP unload
- **Given:** две заявки разных селлеров.
- **When:** seller A list/get B id.
- **Then:** B не в list; get → 404.
- **Negative:** —
