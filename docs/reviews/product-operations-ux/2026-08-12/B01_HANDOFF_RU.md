# Батч 01. Handoff оркестратору

## Что подтверждено

- Реальный in-app Browser подключён к Railway staging; проверка выполнена на DPR 1 при 1280×720 и 1920×1080.
- Реально проверены три роли: fulfillment admin, fulfillment staff с двумя разрешениями, fulfillment seller.
- Admin default landing — `/app/ff/dashboard`; seller default landing — `/seller/documents`; staff default landing — `/app/ff/dashboard`.
- Admin dashboard populated row кликом открыл «Приёмка №000005», статус «В сортировке», две товарные строки, короба и распределение по ячейкам; закрытие вернуло к dashboard.
- Active nav работает на основных routes; browser back/forward/reload работают. Notifications route остаётся без активного пункта sidebar.
- Seller/staff first-login fixtures созданы через UI и подтверждены reload/read-back. Пароли и токены в evidence/log не записаны.
- Seller direct FF URL не даёт FF shell и показывает FF login. Staff direct settings возвращает на dashboard. Staff direct sellers открывает экран с явным сообщением «только администратору», но сам route доступен.

## Блокирующие состояния для продукта

1. `P1`: staff с выданным правом MP видит одновременно `forbidden` и документы/CTA; это тяжёлая несогласованность partial authorization, но B01 не доказывает невозможность завершить весь MP flow или утечку за tenant.
2. `P1`: seller first-login через пустой пароль конфликтует с password autofill и без ручной очистки не запускается.
3. `P1`: dashboard row action визуально скрыт и не keyboard-accessible.
4. `P1`: internal role/status values `fulfillment_seller`, `submitted`, `receiving` видны пользователям.
5. `P1`: 1280×720 обрезает каталог/products по горизонтали.
6. `P1`: «Инвентаризация» обещана меню, но является заглушкой.

## Открытые fixtures

- Нужна безопасная synthetic отгрузка в статусе, который попадает в dashboard «Запланированные отгрузки на склад МП», чтобы проверить row action. Сейчас `BLOCKED_FIXTURE`.
- Нужны synthetic populated seller documents и products без реальных WB данных, чтобы проверить row action/filter/reload. Сейчас `BLOCKED_FIXTURE`.
- Для отдельной проверки profile-loading при контролируемой задержке нужен безопасный network fixture; наблюдаемая короткая загрузка снята, но slow/error recovery не воспроизводился.

## Состояния, которые важно не потерять между батчами

- Admin tenant имеет populated inbound; его данные не изменялись.
- Созданы синтетические B01 seller и staff; оба закончили first-login. Их значения намеренно не дублируются в handoff.
- Staff permissions: «Приёмка» и «Отгрузки на МП» включены и пережили reload.
- Создание shipment, sync WB, добавление ключей, mark-all-read и операции по реальным документам не выполнялись.

## Предлагаемый gate

`ACCEPTED_WITH_BLOCKED_FIXTURES`.

Ориентационный аудит B01 завершён: 64 PNG и sanitized state/network log сохранены, все advertised routes/actions перечислены, reachability отделена от product-process verdict, а неподтверждённые populated-состояния не получили PASS. Populated outbound dashboard и seller rows остаются честными `BLOCKED_FIXTURE` и переданы в процессные батчи B02/B06; это не молча пропущенное покрытие B01. Формальный шаблон gate содержит только `ACCEPTED`, `RETURN_FOR_COVERAGE` и `BLOCKED_FIXTURE`; поэтому при машинном выборе использовать `ACCEPTED`, сохранив квалификатор `WITH_BLOCKED_FIXTURES` в этом handoff.

Следующий батч не начинать до adjudication оркестратора.
