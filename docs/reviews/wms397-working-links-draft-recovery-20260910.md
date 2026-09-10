# WMS-397 / WMS-399 — рабочие переходы и восстановление вложений

Продолжение существующего thread, task-specific отчёт координатору, не новый
бэклог и не приёмка. Проверенный чистый старт и remote:
`08a62fc9c33f08df2f18fdd6ae79ea199892cd0a`, ветка `feat/wms397-chat-mvp`,
worktree `/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-chat-mvp`.
Commit этого отчёта — передаваемый срез; полный проверенный local/remote SHA
сообщается после push. Merge, deploy и изменение канона не выполнялись.

Прочитаны полный собственный `wms397-opus5-followup-20260910.md`, текущие
coordinator handoff/canon и координаторские FfFbsOrdersScreen/ChatDocumentScreen.
Исходная постановка, полный Opus5 и AGENTS прочитаны в сохранённом thread.
Последнее владение соблюдено: App/SellerApp/FfSuppliesShipmentsPage/
FfInboundRequestView/FfFbsSupplyWorkspace не редактировались. Нет других writers,
дочерних агентов, новых страниц, таблиц, статусов, счётчиков или background jobs.
Склад, упаковка, клиентские данные, секреты и запрещённые мобильные источники
не использовались для изменений или проверок.

## Что изменено

Карточка FF ведёт непосредственно в существующую рабочую поверхность. Точный
FBS-заказ разрешается сервером по UUID, tenant, seller и текущим правам через
`GET /operations/chat/documents/fbs_order/{id}/worklist?seller_id={seller}`.
Ответ использует существующий `build_worklist_items`; статус, marketplace и
просрочка берутся с сервера. FfFbsOrdersScreen показывает именно строку заказа,
выставляет его контекст, прокручивает и выделяет рамкой. Фильтр снимается явно
или при смене обычных фильтров. При ошибке права/UUID старые строки и выбор
очищаются; существующая защита от запоздалого ответа сохранена. Это чтение,
без записи складских данных и без новой страницы заказа.

В существующем ChatDocumentScreen для seller MP повторно используется
SellerMarketplaceUnloadDialog. Приёмка продавца ведёт в существующий
`/seller/inbound/:requestId`. Прежняя read-only проекция сохранена для seller
FBS-заказа/поставки и обычной отгрузки: рабочих seller-маршрутов для этих трёх
видов в проверенном SellerApp нет. Новые экраны и расширение FF ACL не добавлены.

При открытии чата composer читает собственные незавершённые загрузки через
`GET /operations/chat/conversations/{id}/draft-attachments`. Можно прикрепить
существующий ID без повторной загрузки либо явно подтвердить удаление файла.
`DELETE .../draft-attachments/{attachment_id}` проверяет доступ к чату,
tenant, uploader, conversation и `message_id IS NULL`. Чужой файл недоступен
даже администратору; отправленный возвращает 409 и не удаляется. User-row lock
сохраняет сериализацию с глобальным бюджетом, attachment-row lock разрешает
гонку с отправкой. SQL delete сначала flush, затем удаление выбранного объекта;
storage error откатывает SQL, возвращает 503 и оставляет возможность повторить.
UI показывает ошибку вне закрытого окна подтверждения и перечитывает список.

SUM/COUNT существующих unlinked attachments по пользователю во всех чатах
tenant остаются единственным источником бюджета 100 MiB / 10 файлов.
Автоматического удаления нет. Ограничение выдачи — 100 строк на чат; при
историческом превышении следующие строки становятся видимыми после разбора
первых. HTML/SVG, raw Content-Type validation, lazy file download, idempotent
send, пакетное чтение карточек и основной чат не переизобретались.

## Проверенные клики и точные маршруты

CUA через Chrome extension доступен. Использованы только собственные прежние
локальные вкладки 663118653/663118654; native focus и чужие вкладки не трогались,
CLI browser automation не применялась. Попытка отдельного скрытого браузера
вернула `Browser is not available: iab`, после чего работа продолжена через
доступное расширение. API 127.0.0.1:8397, Vite 127.0.0.1:5397, только отдельная
`wms397_chat_astra_ui_20260910`; существующая fixture сохранена.

Общий seller fixture: `f9732ee1-5df9-46dc-a661-62963339aaf3`.

| Вид | Целевой маршрут FF и точный fixture ID | Наблюдение этого продолжения |
| --- | --- | --- |
| FBS-заказ | `/app/ff/fbs?order_id=60fd12fc-47a5-4f64-906d-a770ce1562d5&seller_id=f9732ee1-5df9-46dc-a661-62963339aaf3` | Клик открыл существующую таблицу, WB №3970001, CHAT397-TSHIRT, фильтры Wildberries/учебный seller/«Новые», одну строку с рамкой. Проверено AX и снимком. |
| FBS-поставка | `/app/ff/fbs?supply_id=7e4c22de-9095-43c1-a477-5e47532182b0` | Клик открыл рабочее пространство «Учебная FBS-поставка 397», состав с №3970001 / 1 шт. |
| Приёмка | `/app/ff/reception?open_inbound=f62c7525-a5eb-414e-a64e-a75a3089a436` | В собственной старой App открылся только журнал с IN-CHAT397. Обработчик open_inbound находится в coordinator 719ed850 и последующих коммитах; ручная проверка после интеграции остаётся обязательной. |
| MP-отгрузка | `/app/ff/mp-shipments?open_mp=e736e9fa-faa3-42f4-9ef1-c5f7eeb062b5` | Клик открыл существующий рабочий диалог №000397, учебную футболку, план 2. Существующий экран после открытия убирает query. |
| Обычная отгрузка | `/app/ff/mp-shipments?open_outbound=a45dcced-b9ce-42ac-ba67-19b0ed0366ed` | Клик открыл существующие детали заявки draft, CHAT397-TSHIRT, отгружено 0 из 2. Query после открытия убран существующим экраном. |

Под отдельным учебным seller-аккаунтом клик MP-карточки открыл настоящий
SellerMarketplaceUnloadDialog на существующем `/seller/chat/documents/marketplace_unload/{id}`:
учебный склад, черновик, CHAT397-TSHIRT, количество 2, реальные поля/кнопки
документа. Клик приёмки открыл `/seller/inbound/{id}`, №000397, ту же учебную
строку / 2. Ни сохранение, ни передача, ни изменение товаров не нажимались.

Для восстановления созданы только два disposable учебных файла:
`recover-reopen-wms397.txt`, `discard-explicit-wms397.txt`. После переоткрытия
чата склад нажал «Прикрепить» и отправил первый, для второго подтвердил
«Удалить файл». Первый виден в ленте обоим аккаунтам, список черновиков исчез.
Read-only SQL после кликов: первый filename — ровно 1 row и 1 non-null
message_id; второго filename — 0 rows. API-тест отдельно подтверждает сохранность
байтов восстановленного файла и отсутствие повторной загрузки. Клиентские файлы
не удалялись. Физический Ctrl+V Windows и новый paste/retry проход в этом
продолжении не выполнялись; предыдущие доказательства сохранены в отчётах.

## Проверки

- Полный **только scoped** `tests/test_chat_api.py`: PostgreSQL 24 passed (40.24 s), SQLite 22 passed / 2 skipped (36.18 s). Два skip — PostgreSQL row-lock concurrency; на PostgreSQL оба прошли.
- После последней перестановки SQL flush перед физическим discard: два затронутых PostgreSQL теста повторены — 2 passed / 22 deselected (4.20 s); SQLite recovery — 1 passed / 23 deselected (2.39 s).
- Новые проверки: uploader-only recovery; чужой tenant/чат/автор; revoked extra membership для staff/admin; 401/403/404; storage failure/rollback/retry; attached-file 409 без удаления байтов; освобождение общего бюджета; пять конкурентных delete-versus-attach пар без потери отправленного файла/пустого сообщения; точные WB/Ozon UUID при одинаковом внешнем номере, expired/done/packed и запрет seller/restricted FF.
- Ruff пяти затронутых backend-файлов — PASS; mypy API, двух services и chat model — PASS (4 files). Модель меняет только устаревший комментарий членства, схема не меняется.
- ESLint chat components/screens, `npx tsc --noEmit -p tsconfig.app.json`, `RAYON_NUM_THREADS=2 npm run build` — PASS. Существующий Vite chunk warning >500 kB сохраняется.
- FfFbsOrdersScreen ESLint — прежняя ошибка `setNearViewport` line 233 и warning missing `openWorkspace`. Отдельный stdin lint исходного `08a62fc9` воспроизводит те же два замечания; deep-link diff их не добавляет. Общий lint этого файла не объявляется зелёным.
- `git diff --check` и read-only `git apply --check` интеграционного патча в coordinator — PASS. Полного pytest, xdist, deploy нет; максимум два однопроцессных scoped теста одновременно.

## Передача и незакрытые границы

Opus5 #4: восстановление и явный discard записанных в SQL собственных drafts
реализованы и проверены, старое требование отдельного разрешения на routine UI
obsolete после прямого поручения владельца. Opus5 #10: FF order исправлен до
реальной строки, FF supply/MP/outbound проверены; FF inbound остаётся
интеграционной проверкой, seller inbound/MP проверены, три отсутствующие seller
рабочие поверхности остаются ограничением. Прежние #1/#2 obsolete; #3/#5/#6/#7/#8/#9
не переоткрываются этим diff, adversarial regression входит в scoped файл.

Для координатора подготовлен узкий
`artifacts/wms397-working-links-coordinator-20260910.patch` только для
FfFbsOrdersScreen и ChatDocumentScreen относительно его текущего содержимого.
Трёхстороннее построение сохраняет coordinator dirty/URL/context guards,
`open_inbound`, supply_id и onDirtyChange. Patch проверен без записи в coordinator.
Это помощь при конфликте cherry-pick, не второй комплект изменений для применения
поверх уже успешно перенесённых строк. App/SellerApp-патч не требуется: общий
inbound handler уже реализован координатором. Не подменять его FBS файл целиком
версией из worker и не откатывать 719/857/e3aac навигацию.

Остаются обязательными независимое review итогового SHA и клики после интеграции:
FF inbound, Back/Forward/Reload, exact order → supply → close при сохранении
координаторских guards, revoked/restricted UI. SQL-тесты не заменяют эти клики.
Удалённое object storage, CI и staging/production не проверялись.

Существующая граница SQL/storage сохраняется: crash/commit failure после
успешного физического удаления может оставить SQL draft с отсутствующим объектом;
объект после неуспешного upload commit может не иметь SQL строки и не попадёт в
recovery. Новая транзакционная сущность/автоуборка для этого не вводились. Drafts
из чата с отозванным доступом нельзя показать/удалить, пока доступ не восстановлен;
они продолжают учитываться в глобальном бюджете. Эти ограничения не скрываются
под статусом «полностью принят».

Точные файлы среза:

- `backend/app/api/chat_routes.py`
- `backend/app/models/chat.py` (только комментарий)
- `backend/app/services/chat_document_service.py`
- `backend/app/services/chat_service.py`
- `backend/tests/test_chat_api.py`
- `frontend/src/components/chat/AttachedDocCard.tsx`
- `frontend/src/components/chat/ChatComposer.tsx`
- `frontend/src/components/chat/chatApi.ts`
- `frontend/src/components/chat/documentTarget.ts`
- `frontend/src/screens/chat/ChatDocumentScreen.tsx`
- `frontend/src/screens/v2/FfFbsOrdersScreen.tsx` (только deep-link delta)
- этот отчёт и указанный интеграционный `.patch`.

Координатору: обновить только свои canonical cards/handoff по указанным
resolved/obsolete/pending фактам после независимого review. Worker DONE не
означает приёмку WMS-397/399 и не разрешает deploy.
