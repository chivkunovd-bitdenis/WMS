# F23 Combined Product+Design Rereview: seller catalog cleanup rework

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: повторный isolated Product+Design gate Agent.
Статус: `PRODUCT_DESIGN_APPROVED_FOR_DEV`.

Код не редактировался. Verdict дан именно по rework spec
`docs/reviews/product-operations-ux/2026-08-12/evidence/f23-ba-ux-rework/F23_BA_UX_REWORK_SPEC_RU.md`,
а не по текущему плохому экрану seller catalog.

## Короткий verdict

F23 можно отдавать в atomic dev по rework spec.

Причина: rework spec закрывает оба исходных blocker-а - продуктовый и визуальный.
Новая модель больше не предлагает опасное действие "всем товарам" без выбора
строк, убирает `Лимит`, регулярные chips, technical statuses и broken layout из
основной таблицы, а также явно сохраняет F22 safe-sync инвариант: unknown не
становится `0`, success появляется только после readback, safe zero требует
отдельного опасного подтверждения.

Это не означает, что F23 готова как фича. Это approval только на следующий gate:
один atomic dev agent может реализовать F23 seller catalog cleanup строго в
границах rework spec. После dev обязательны code review и живой browser product
QA.

## Проверка основного сценария

Сценарий `select rows -> one bulk action -> confirm -> result` описан достаточно
конкретно для разработки:

1. Пользователь открывает `Товары`.
2. Выбирает одну или несколько строк чекбоксами.
3. Видит `Выбрано N` и ровно одно основное bulk-действие `Изменить публикацию`.
4. Выбирает одно действие: `Включить`, `Поставить на паузу`, `Повторить
   отправку` или `Настроить FBS-пул`.
5. Для изменения публикации видит confirmation dialog с количеством выбранных
   товаров, первыми 5 товарами/SKU и текстом `Будут изменены только выбранные
   товары`.
6. После подтверждения backend получает только выбранные `product_ids`.
7. UI показывает результат по выбранным строкам: сколько обновлено, сколько
   пропущено и почему; невыбранные строки не меняются.

Это правильная складская последовательность: сначала видимый набор товаров,
потом действие, потом подтверждение, потом человеческий результат.

## Что должно исчезнуть из основного экрана

Rework spec прямо запрещает элементы, из-за которых initial product/design review
был rejected:

- `Лимит` как постоянное поле, chip или колонка основной таблицы;
- `Включить всем`, `Выключить всем`, `Пауза публикации всем` и любой основной
  путь с `product_ids: null`;
- регулярные chips `Заполнено`, `Нет ТЗ`, `ЧЗ` и sync chips, если это не редкая
  ошибка или исключение;
- raw technical statuses и backend-коды вроде `pending_confirmation`,
  `warehouse_mapping_missing`, `wb_upstream_error_500`, `conflict`, raw JSON или
  stack trace;
- длинные статусы внутри строки вроде `Не удалось отправить остаток в WB` и
  `Ещё не уходил`;
- black strip, непрокрашенный край shell, body-level horizontal overflow и
  скрытое обрезание действий.

Эти запреты достаточно однозначны: dev и code review смогут проверить не только
наличие нового selection flow, но и отсутствие старого UI-шума.

## Compact table на 1280 px

1280 px requirement в spec достаточно конкретен. Таблица должна показать
приоритетные рабочие данные без раздувания:

- `Выбор` - 4%;
- `Товар` - 28-30%;
- `WB / ШК` - 12-14%;
- `Остаток` - 13-15%;
- `FBS-пул` - 10-12%;
- `Публикация WB` - 13-15%;
- `ТЗ / ЧЗ` - 8-10%;
- `Действия` - 6-8%.

Дополнительно заданы проверяемые правила геометрии: `document.documentElement.scrollWidth <= window.innerWidth`
на 1280x720, 1366x768 и 1920x1080; row height 56-64 px, максимум 72 px; название
до 2 строк; SKU/ШК/nmID/артикул с ellipsis; row actions 28-32 px; switch 40-48
px. Этого хватает, чтобы design review и browser QA не спорили о вкусе, а
проверяли конкретные размеры и видимый результат.

## F22 safe-sync

F22 safe sync не нарушается, если dev реализует spec буквально.

Ключевые guardrails сохранены:

- FBS-пул остается в распределении остатка; публикация WB не создает и не меняет
  FBS-пул напрямую.
- `fbs_stock_limit` не является источником safe zero и не живет в основной
  таблице.
- Missing/unknown availability, ошибка WB, empty availability, mapping miss и
  bulk enable не превращаются в `0`.
- Строка с `FBS-пул = 0` показывает `Нет FBS`, disabled/недоступную публикацию и
  путь к настройке FBS-пула, а не успешную публикацию.
- Success `WB: N шт` разрешен только после readback по тому же seller +
  warehouse + chrtId.
- `Отправить 0 шт` допустимо только как отдельный опасный путь для явного FBS
  zero с отдельным подтверждением.

Таким образом, F23 cleanup не ослабляет F22. Наоборот, он делает F22 видимым и
менее опасным в seller catalog.

## Конкретность gate-ов после dev

Критерии для atomic dev, code review и browser QA достаточны.

Для dev есть проверяемый checklist: selection model, selected-only bulk request,
отсутствие "всем", отсутствие `Лимит`, короткие F22 statuses, no regular chips,
compact row actions, 1280 layout, сохранность распределения и ТЗ.

Для code review есть проверяемые запреты: нет whole-catalog bulk без выбора, нет
technical enum/status/debug в основной таблице, нет `fbs_stock_limit` как row
field, нет склейки unknown с safe zero, confirmation обязателен, layout чинится
причиной, а не скрытым обрезанием.

Для browser QA есть живой путь с evidence: открыть seller catalog на 1280x720,
1366x768 и 1920x1080; сделать screenshot и DOM read-back; пройти no-selection,
selection, confirmation, selected-only result; проверить `FBS-пул = 0`, статусы
`Пауза`, `Проверяем WB`, `WB: N шт`, `Ошибка WB`; открыть drawer распределения и
ТЗ; проверить F22 incident path `20 -> 20` при отсутствии FBS-пула.

Рекомендуемое test coverage в spec тоже достаточно предметное: оно требует
user-visible outcome, negative/restriction cases и отдельный 1280 layout case.

## Условия approval

Dev можно начинать только в узком scope F23 seller catalog cleanup:

- не чинить соседние фичи "заодно";
- не возвращать глобальные actions "всем";
- не менять F22 safe-sync модель в сторону publishable fallback zero;
- не делать новый общий redesign seller portal;
- не считать F23 done до `CODE_REVIEW_PASSED` и `BROWSER_PRODUCT_QA_PASSED`.

## Итог

`PRODUCT_DESIGN_APPROVED_FOR_DEV`.

F23 можно отдавать в atomic dev по rework spec. Текущий экран как он есть по-прежнему
не accepted; approved именно переработанная спецификация и только как вход в
следующий gate разработки.
