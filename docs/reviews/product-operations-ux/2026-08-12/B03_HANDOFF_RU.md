# Батч 03. Handoff оркестратору

## Короткий ответ

Физическая приёмка технически проводит товар из submitted в Sorting и корректно создаёт sorting-only stock, но процесс **не готов к самостоятельной работе низкоквалифицированного приёмщика**. Основная проблема не в красоте экрана: сотрудник должен помнить identity между queue/detail, возвращать focus, понимать скрытое сложение loose+box, сам считать прогресс и знать, что план коробов не является guard. Один click `Редактировать` после completion без предупреждения отменяет уже состоявшийся межзонный handoff.

## Что реально выполнено

- Все проверки проходили в настоящем in-app Browser на Railway staging.
- Exact synthetic inbound найден не по порядку строки, а доказан seller/date/2 lines, №000007, двумя SKU/barcode, планом A=3/B=2 и boxes=2.
- Пройдены populated queue, row/detail, 1280 и честный 1920, empty/unknown/valid/repeat scan, negative/decimal/blank/overage/manual recovery, boxes create/double-click/fill/error/composition/delete, discrepancy/cancel, completion/double-click, reload, reopen/re-complete, Sorting handoff и FF stock semantics.
- Каждая мутация прочитана обратно после reload либо через следующий серверный экран.
- Сохранено **58 PNG**, лично открыто через `view_image`: **58/58**; у каждого есть отдельный visual verdict.
- Checklist: **73/73 adjudicated**, фактически выполнено **66/73**.

## Checklist counts

- `PASS`: **45**.
- `FRICTION`: **4**.
- `FAIL_PROCESS`: **8**.
- `FAIL_UX`: **9**.
- `BLOCKED_ENV`: **2**.
- `BLOCKED_FIXTURE`: **1**.
- `NOT_RUN`: **3**.
- `N/A`: **1**.

Семь невыполненных по факту пунктов не скрыты: mismatch candidate был неприменим; print waybill и box label не дали доказуемого preview; unsaved manual Cancel и explicit zero+reload не прогнаны; seller read-back заблокирован отсутствием safe seller session.

## Главный UX verdict

Фактически пройденный no-box happy path требует 8 input events с идеальным hardware scanner либо до 12 в наблюдённом keyboard-пути из-за focus recovery. Это не страшное число кликов, но путь имеет пять смен точки внимания и требует помнить seller между экранами. Реальная работа с двумя плановыми коробами требует минимум 14 input events и скрытого знания, что loose fact и box composition складываются.

Минимальный идеальный flow остаётся в тех же экранах: различимая row с номером и totals; seller+progress в header; постоянный scan focus; Create box сразу открывает fill; общий fact вычисляется из box/loose, а не редактируется независимо; одна completion CTA и конкретные discrepancy deltas. Получается 8 событий без коробов или 12 с двумя коробами — без redesign и нового workflow.

## Product stop-gates

1. Reception queue смешивает drafts и рабочие документы, не показывает human number/totals и выводит raw status; row mouse-only.
2. Detail не показывает seller и compact progress, поэтому identity и коробный план нужно помнить.
3. Keyboard/manual scan и edit теряют focus; one-hand поток требует возврата к мыши.
4. Loose fact + box scan двойным счётом увеличивают accepted total; система не объясняет модель.
5. План `2` коробов никак не влияет на completion: с нулём коробов документ ушёл в Sorting без warning.
6. Discrepancy confirm не называет SKU/delta/consequence.
7. Decimal quantities silently floor в line и box; blank silently ignored.
8. `Редактировать` одним click без confirmation возвращает completed документ в Reception и снимает весь stock из Sorting.

## Что работает

- Unknown scan и negative quantity дают конкретные русские ошибки и не мутируют факт.
- Valid scan считает ровно одну физическую единицу, repeat sequence и ручной факт durable.
- Overage/underage заметны, Cancel completion честно оставляет Receiving.
- Double-click Create и Completion не создают видимых дублей.
- Непустой box защищён от удаления; composition переживает reload.
- Completion убирает document из Reception, создаёт одну Sorting row с remaining=5.
- FF stock semantics после final completion корректны: A/B `3/2` в Sorting, `available=0` до размещения.

## Final staging state для B04

- Request ID: `41823675-2b08-4714-97b6-8782486c4dda`.
- Документ: №`000007`, seller `B01 UX Seller 960724`, plan date `2026-08-12`.
- Accepted: A=`3`, B=`2`, total=`5`.
- Status: `sorting`; в Reception отсутствует, в Sorting присутствует с remaining=`5`.
- Synthetic boxes: `0`; тестовый box очищен и удалён.
- FF stock: A=`3`, B=`2`, только зона Sorting; available=`0`.
- B04 distribution/putaway не выполнялись.

Документ был один раз controlled-reopened для проверки опасной CTA, затем повторно завершён. Финальное состояние прочитано обратно и пригодно как B04 fixture.

## Recovery и непокрытое

- Reload Reception detail теряет open document; Back/Forward на Sorting detail рассинхронизируют route и видимый dialog.
- Explicit manual zero и его reload не проверены; исходный 0 не выдаётся за эту проверку.
- Отдельный unsaved manual Cancel не проверен.
- Waybill/box label print reachability видна, но preview/output не доказаны.
- Seller product read-back не выполнен без safe seller session.
- Параллельная работа двух сотрудников и offline/slow-network не входили в доступный Browser fixture и не получают PASS.

## Gate

Формальный gate доказательств B03: **`ACCEPTED`** — все 73 строки имеют конечный статус, 58/58 изображений лично adjudicated, exact state и reload read-back сохранены, ограниченные кадры и пропуски не выданы за PASS.

`ACCEPTED` относится только к полноте и честности этого review batch. Продуктовый процесс получает **STOP перед несопровождаемым пилотом** до закрытия P1/P0 gates выше. B04 можно начинать только после оркестраторской проверки handoff; сам B03 распределение по ячейкам не выполнял.

## Git boundary

B03 не менял application code и не выполнял commit/push. Созданы только review docs и evidence в общей review-ветке; сохранение в Git выполняет оркестратор по общему контракту, не этот изолированный reviewer.

