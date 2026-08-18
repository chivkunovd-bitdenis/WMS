# F18 Product / UX Review — возвраты как вариант приемки

Дата проверки: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
HEAD на момент проверки: `cf5aa16ea5214671f515be3cbc358c33bd9522a7`.

Важно: проверка выполнена по текущему грязному worktree. Код реализации не редактировался.

## Verdict

`PRODUCT_REWORK_REQUIRED`

## Rationale

Идея F18 продуктово правильная: возврат действительно не должен превращаться в отдельный складской процесс. В текущей реализации это частично соблюдено: backend хранит `operation_type`, принимает `inbound|return` в том же endpoint заявки приемки, а FF-карточка открывается та же самая и показывает тип операции как понятный русский текст.

Но пользовательский путь создания возврата сейчас не закрыт. В seller portal на экране документов есть только действие `Создать заявку на поставку`, оно ведет в `/inbound/new`, а `SellerInboundDraftScreen` при автосоздании черновика отправляет только `warehouse_id` и `planned_delivery_date`. `operation_type` туда не передается. Значит обычный селлер не может создать возврат из UI; возврат в e2e создается напрямую API-запросом с `operation_type: 'return'`. Для Product gate это не проходит: BA-проверка говорит "можно создать возврат", а не "можно послать технический JSON".

Второй риск — возврат прячется в списках. Seller documents получает от API строки inbound, но локальный `InboundSummaryRow` не хранит `operation_type`, а таблица всегда показывает такой документ как `Поставка`. FF-очередь приемки тоже не показывает тип операции до открытия карточки. Это не создает лишний процесс, но как сотрудник склада я узнаю, что передо мной возврат, только когда уже открыл документ.

FF-карточка приемки в целом выглядит пригодно: тип `Возврат` виден в компактной шапке, обычная приемка остается default-вариантом, отдельной вкладки или dashboard для возврата не появилось. Seller factual card тоже умеет показать `Карточка приёмки · Возврат` и summary `Тип операции: Возврат`, если документ уже создан как return. Это хорошая база, но она не компенсирует отсутствие UI-входа.

Печать частично различает возврат: в metadata документа может быть `Возврат №...`, потому что FF-карточка передает `documentTypeLabel`. При этом главный заголовок печатной формы остается `Накладная — приёмка на склад ФФ`, поэтому распечатка не является однозначной "с первого взгляда" для возврата.

## Required Rework

1. Дать селлеру пользовательский способ создать возврат в том же процессе приемки. Без новой вкладки и отдельного dashboard: лучше компактный выбор типа операции до создания черновика или split/menu у действия создания, где варианты называются по-человечески `Поставка` и `Возврат`, а не `inbound/return`.
2. Протащить `operation_type` в seller documents list и FF queue на уровне подписи документа. Не добавлять лишние колонки, если можно пометить существующую ячейку документа или типа: `Поставка` для обычной приемки и `Возврат` для возврата.
3. Сделать печатную форму возврата однозначной в главном заголовке или первом блоке: оператор должен видеть `Возврат`, не выискивая это в metadata.
4. Добавить e2e, который создает возврат через seller UI, открывает его в FF-приемке и проверяет видимый `Возврат` в FF-card, seller factual card и печати. Текущий API-seeded return-тест полезен, но не доказывает пользовательский сценарий создания.

## Screens Checked

- Seller documents: `frontend/src/screens/v2/SellerDocumentsScreen.tsx`.
- Seller create/draft card: `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`.
- Seller app route wiring: `frontend/src/apps/seller/SellerApp.tsx`.
- FF reception queue: `frontend/src/screens/ff/FfInboundQueuePage.tsx`.
- FF inbound/request card: `frontend/src/screens/ff/FfInboundRequestView.tsx`.
- Inbound print: `frontend/src/utils/printShipmentWaybill.ts`.
- Backend operation type path: `backend/app/api/inbound_intake.py`, `backend/app/services/inbound_intake_service.py`, `backend/app/models/inbound_intake.py`, `backend/alembic/versions/20260812_0079_inbound_returns_dimensions_fact_lines.py`.
- Tests read: `backend/tests/test_inbound_intake.py`, `frontend/tests-e2e/inbound-receiving-v2.spec.ts`.

Browser QA was not run. This verdict is a Product / UX review by source and test reading, not a substitute for future Browser Product QA.

## Assumptions

- Primary creator of a return request is the seller portal user.
- F19 auto-print behavior is adjacent and was only considered where it appears in the same FF card.
- Technical codes `inbound` and `return` must not be visible to warehouse or seller users.
