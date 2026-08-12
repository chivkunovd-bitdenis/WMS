# Browser execution checklist — продуктовый прогон staging

## Контракт выполнения

- Среда: только staging `web-production-9e7c1.up.railway.app`; production и локальный runtime запрещены.
- Runtime-взаимодействие выполняет оркестратор в своём Browser по этому независимому чек-листу. Продуктовый агент после получения файлов сам просматривает полноразмерные изображения через `view_image` и выносит визуальное заключение.
- Разрешённые staging credentials используются только для входа. Email, пароль, токен, cookie и заполненная форма входа не попадают в скриншоты, отчёты и сообщения.
- Действия, меняющие данные, выполняются только на заранее выделенном staging test object. Если объект не выделен или cleanup не доказан, действие получает `BLOCKED_SHARED_DATA`, а не выполняется.
- Никаких действий с API-ключами, токенами WB/ЧЗ, секретными полями и кабинетами ключей. Настройки credentials открывать только до карточки статуса, не открывая форму и не вводя значения.
- Каждый screenshot — полный viewport без обрезки. Имена: `<scenario>__<role>__<viewport>__<step>.png`, где `step` = `before|action|result|reload|failure`.
- Для ключевых экранов повторить `before` и `result` на `1280x720` и `1920x1080`. Для остальных достаточно `1280x720`, если в строке не указано иное.

## Приоритет 0 — baseline и доступ

### PROD-AUTH-001 — публичный вход и возврат после logout

- Роль: anonymous → `fulfillment_admin`.
- URL: `/`.
- Действия:
  1. Открыть пустую форму входа. Не вводить staging email до скриншота.
  2. Проверить переключение «Вход» / «Регистрация» и возврат на «Вход» без отправки формы.
  3. Выполнить вход разрешёнными credentials без screenshot заполненных полей.
  4. Зафиксировать первый защищённый экран, роль, навигацию и отсутствие наложения auth-форм.
  5. Обновить страницу.
  6. Нажать `Выйти`; зафиксировать возврат на публичный экран с очищенными полями.
- Failure: отправить вход с синтетическим несуществующим email и неверным паролем; после появления ошибки очистить поля до screenshot, если браузер сохраняет значение.
- Evidence:
  - `PROD-AUTH-001__anonymous__1280x720__before.png`
  - `PROD-AUTH-001__ff_admin__1280x720__result.png`
  - `PROD-AUTH-001__ff_admin__1280x720__reload.png`
  - `PROD-AUTH-001__anonymous__1280x720__failure.png`
  - `PROD-AUTH-001__ff_admin__1920x1080__result.png`

### PROD-SHELL-001 — полный shell и каждый пункт навигации

- Роль: `fulfillment_admin`.
- Начало: `/app/ff/dashboard` обычным путём после входа.
- Нажать по одному разу: `Дашборд`, `Отгрузки на МП`, `FBS`, `Приёмка`, `Сортировка`, `Упаковка`, `Ячейки`, `Селлеры`, `Каталог`, `Инвентаризация`, `Честный знак`, `Настройки`, колокольчик уведомлений.
- Для каждого шага записать конечный URL, заголовок экрана, loading/empty/error и наличие очевидного следующего действия. Если пункт скрыт — записать `N/A_BY_ROLE`.
- После прямого URL `/app/does-not-exist` зафиксировать редирект и понятность результата.
- Evidence: один `before` для dashboard и по одному `result` на каждый конечный экран; ключевые dashboard и FBS — два viewport.

## Приоритет 1 — FBS, физическая сборка и передача

### PROD-FBS-001 — список заказов и FBS baseline

- Роль: `fulfillment_admin`.
- URL через меню: `/app/ff/fbs`.
- Действия:
  1. Зафиксировать вкладку `Новые` до действий в 1280×720 и 1920×1080.
  2. Нажать все видимые вкладки (`Новые`, `В работе`, `В доставке`, `Завершённые`) и вернуться в `Новые`.
  3. Использовать поиск: существующий товар и строка, не дающая результатов; нажать `Найти`.
  4. Использовать доступные фильтры селлера/склада/маршрута по одному разу; вернуть исходное значение.
  5. Навести на фотографию товара; отдельный screenshot увеличенного preview.
  6. Выбрать один доступный заказ; затем второй совместимый; открыть preflight/диалог формирования поставки, но не подтверждать создание без выделенного test set.
  7. Выбрать несовместимый или заблокированный заказ, если такой есть, и зафиксировать человекочитаемую причину.
  8. Снять выбор, reload и проверить отсутствие ложного создания.
- Проверить baseline: `Товар`, `Селлер`, `Маршрут сдачи`, `Отгрузить до`; вне `Новые` допустим `Статус`. Не должно быть шестиколоночной старой таблицы, `Подробнее`, технических складов, внутренних ID и лишних чипов.
- Evidence:
  - `PROD-FBS-001__ff_admin__1280x720__before.png`
  - `PROD-FBS-001__ff_admin__1280x720__action.png`
  - `PROD-FBS-001__ff_admin__1280x720__result.png`
  - `PROD-FBS-001__ff_admin__1280x720__reload.png`
  - `PROD-FBS-001__ff_admin__1280x720__failure.png`
  - `PROD-FBS-001__ff_admin__1920x1080__before.png`
  - `PROD-FBS-001-PHOTO__ff_admin__1280x720__action.png`

### PROD-FBS-002 — существующая поставка, этап «Состав»

- Роль: `fulfillment_admin`.
- Вкладка `В работе`; найти разрешённый тестовый supply (live-stand fixture допускает поиск товара `Резинки пружинки`).
- Открыть строку поставки кликом по содержательной области, не по специальной кнопке.
- Проверить вкладки ровно `Состав`, `Подбор`, `Упаковка и маркировка`, `Короба`.
- Действия: открыть `Печать листа подбора` до preview и закрыть; нажать `Начать работу с поставкой` только если test supply ещё на этом этапе и выделен для мутации; повторный клик во время busy; reload после результата.
- Failure: если кнопка доступна и есть безопасный fault-fixture — временный failure/timeout. Иначе `BLOCKED_NO_FAULT_FIXTURE`.
- Проверить физический контекст: оператор держит лист подбора или пустую тележку; экран должен сказать, что брать дальше и не требовать догадки.
- Evidence: `PROD-FBS-002__ff_admin__1280x720__before|action|result|reload|failure.png`.

### PROD-FBS-003 — подбор: ручной и сканерный путь

- Роль: `fulfillment_admin` или `fulfillment_staff(packaging)`; если второй роли нет — `BLOCKED_AUTH_ROLE`.
- В существующей поставке открыть `Подбор`.
- Действия:
  1. Зафиксировать верхний сканерный блок и общий прогресс.
  2. В ручной строке открыть список ячеек; проверить, что видны только места с товаром и готовое `Снять N шт.`.
  3. Если выделенный объект допускает mutation — снять рассчитанное количество, затем доступный `Вернуть/Отменить подбор`; reload после каждого результата.
  4. В сканере ввести заведомо неверный синтетический ШК ячейки и затем товара; зафиксировать точную ошибку и сохранение прогресса.
  5. Не вводить реальный складской barcode в shared supply без выделенного объекта.
- Viewports: 1280×720 полный пакет; 1920×1080 `before` и `result`.
- Evidence: `PROD-FBS-003__ff_admin__1280x720__before|action|result|reload|failure.png`, `...__1920x1080__before|result.png`.

### PROD-FBS-004 — упаковка и маркировка

- Открыть `Упаковка и маркировка` у выделенного supply.
- Проверить строку = один заказ, соседство одинаковых товаров, фото/артикул/ШК/номер заказа WB.
- Использовать каждый элемент:
  - `ТЗ на упаковку` → открыть и закрыть;
  - `Печать QR` → открыть preview и закрыть, не отмечая физическое нанесение;
  - `Печать` → открыть стандартный `MarkingPrintDialog`, переключить доступные варианты ЧЗ/ШК, закрыть без подтверждения;
  - меню `⋮` → открыть и закрыть режим перепечатки;
  - `Печать всего` → открыть общий конструктор и закрыть без расходования пула, если нет отдельного test pool;
  - `Всё упаковано` — только на выделенном supply; затем reload.
- Failure: строка/поставка с нехваткой ЧЗ либо безопасный серверный blocker. Проверить один понятный итог сверху и явную пометку строки, без технического текста.
- Не выполнять и не скриншотить экран, если он раскрывает реальные коды ЧЗ. На screenshots коды должны быть маскированы приложением либо сценарий `BLOCKED_SECRET_EVIDENCE`.
- Evidence: `PROD-FBS-004__ff_admin__1280x720__before|action|result|reload|failure.png`, `...__1920x1080__before|result.png`.

### PROD-FBS-005 — короба, маршрут ПВЗ

- Только выделенный test supply маршрута ПВЗ.
- Действия:
  1. Добавить один короб; затем ещё один через поле количества.
  2. Развернуть/свернуть строку каждого короба.
  3. Открыть `Добавить товары`, использовать поиск, изменить количество, подтвердить одну позицию.
  4. Удалить позицию из состава, вернуть её снова.
  5. Открыть `QR` до preview и закрыть.
  6. Меню `⋮`: попытка удалить непустой короб → failure; очистить → подтверждение → результат; удалить пустой короб → результат.
  7. Reload после каждого необратимого шага; сравнить количество/состав/QR.
- Не нажимать `Передать в WB` без заранее выделенного полного supply и recovery plan.
- Evidence: `PROD-FBS-005__ff_admin__1280x720__before|action|result|reload|failure.png`, `...__1920x1080__result.png`.

### PROD-FBS-006 — короба, маршрут склад/СЦ и передача

- Только выделенный test supply маршрута `Склад / СЦ`.
- Повторить создание/наполнение/очистку/удаление коробов из PROD-FBS-005.
- Проверить, что нет кнопки QR короба и нет технической надписи вместо неё.
- `Передать в WB`: нажать только на полном выделенном supply после screenshot свежего состояния; зафиксировать confirmation, result и reload.
- Если deliver подтверждён, проверить `Печать QR поставки`. Если deliver успех, а QR failure — должен быть безопасный retry только QR без повторной передачи.
- Failure: неполностью распределённый товар или отсутствующий обязательный шаг; серверная ошибка должна оставаться на том же экране и объяснять, что делать.
- Evidence: `PROD-FBS-006__ff_admin__1280x720__before|action|result|reload|failure.png`, `...__1920x1080__result.png`.

### PROD-FBS-007 — FBS stock-sync граница администратора

- URL: `/app/ff/fbs/stock-sync`; открыть через FBS section nav, не прямым URL.
- Использовать вкладки/селлер/склад/поиск/refresh. Проверить normal, empty и error.
- Не менять binding, stock-sync toggle и не запускать WB sync без выделенного seller/warehouse и recovery plan.
- Зафиксировать, что техническая настройка отделена от основного operator flow и доступна только admin.
- Evidence: `PROD-FBS-007__ff_admin__1280x720__before|action|result|reload|failure.png`.

## Приоритет 1 — приёмка, сортировка, упаковка, MP outbound

### PROD-INB-001 — очередь «Приёмка» и документ

- URL через меню: `/app/ff/reception`.
- Действия очереди: каждый фильтр/сортировка/поиск, открыть строку, закрыть full-screen document, открыть повторно, reload.
- В документе использовать все видимые вкладки и безопасные действия. Print: открыть `Печать накладной` preview и закрыть. Короба: открыть печать одного/всех внутренних ШК только до preview.
- Failure: неверный синтетический barcode в доступном scanner input; отсутствие строки/пустой список.
- Mutation (`Принять по коробам`, scan actual item, `Завершить приёмку`, putaway) — только isolated request с известным ожидаемым количеством и cleanup; иначе `BLOCKED_SHARED_DATA`.
- Evidence: `PROD-INB-001__ff_admin__1280x720__before|action|result|reload|failure.png`, `...__1920x1080__before|result.png`.

### PROD-SORT-001 — очередь «Сортировка» и раскладка

- URL: `/app/ff/sorting`.
- Открыть строку, проверить остаток в зоне сортировки, подсказки ячеек, скан/ручное количество, действие раскладки, вход в упаковку.
- Failure: неизвестная ячейка/товар или количество выше остатка на isolated request.
- Reload после частичной раскладки; проверить, что следующий шаг и остаток понятны.
- Evidence: `PROD-SORT-001__ff_admin__1280x720__before|action|result|reload|failure.png`.

### PROD-PACK-001 — общая очередь упаковки

- URL: `/app/ff/packaging`.
- Использовать вкладки/фильтры/поиск/refresh; открыть существующее задание; закрыть и открыть повторно.
- В задании: каждая строка, ТЗ, ввод прогресса, стандартная печать, переход к связанному MP document и назад. Mutation pack/complete только isolated task.
- Перейти по ссылке `Ожидают маркировки`; проверить `/app/ff/packaging/pending-marking`, возврат назад, normal/empty/error.
- Failure: ноль, отрицательное или превышающее остаток количество в isolated task; либо `BLOCKED_SHARED_DATA`.
- Evidence: `PROD-PACK-001__ff_admin__1280x720__before|action|result|reload|failure.png`, `...__1920x1080__before|result.png`.

### PROD-MP-001 — отгрузка на МП

- URL: `/app/ff/mp-shipments`.
- Использовать каждый фильтр/таб/поиск; открыть строку MP document; проверить вкладки `Товары` и `Упаковка`, print invoice, boxes, pick, confirm/ship blockers.
- Создание нового draft и его cancel допустимы только для isolated staging seller/warehouse; имя/комментарий с префиксом `REVIEW-PRODUCT-20260812`.
- Failure: нажать `Создать отгрузку на МП` при отсутствующем обязательном выборе либо открыть isolated draft без строк и попытаться подтвердить.
- На dashboard кликнуть одну MP-shipment строку и проверить, что открывается `/app/ff/mp-shipments`, а не dashboard/wildcard.
- Evidence: `PROD-MP-001__ff_admin__1280x720__before|action|result|reload|failure.png`, плюс `PROD-MP-DASH-LINK__ff_admin__1280x720__result.png`.

## Приоритет 2 — каталоги, настройки, движения и заглушки

### PROD-CATALOG-001 — каталог товаров

- `/app/ff/products`: поиск, seller filter, pagination, photo hover, открыть/закрыть ТЗ упаковки, import preview без apply, refresh.
- Не сохранять ТЗ и не выполнять import apply без isolated product.
- Full package 1280; before/result 1920.

### PROD-CELLS-001 — склады и ячейки

- `/app/catalog`: выбрать каждый доступный склад, открыть racks/locations, suggest location, формы создания склада/ячейки/товара без submit, barcode print preview.
- Не создавать реальные объекты без isolated namespace/cleanup.

### PROD-SELLERS-001 — селлеры и staff accounts

- `/app/ff/sellers`: search/filter/refresh, открыть формы добавления селлера и сотрудника, permissions dialog; закрыть без submit.
- Не создавать учётные записи и не менять пароль/permissions без isolated account.

### PROD-HS-001 — Честный знак

- `/app/ff/honest-sign`: tabs/filters/search/pagination; открыть pool и product; ledger, export dialog, reprints, pending marking links; back/reload.
- Не открывать полный код КМ в screenshot и не выполнять print/defect/reprint mutations без isolated pool.

### PROD-SET-001 — настройки ФФ

- `/app/ff/settings`: открыть все несекретные секции, формы staff/permissions/rate and feature toggles без сохранения.
- Не открывать secret credentials forms, не менять address storage, feature flags и permissions.

### PROD-MOVE-001 — движения и transfer

- `/app/ops/movements`: refresh, digest start только если он read-only and isolated; reload polling result.
- `/app/ops/transfers`: открыть selectors, failure на пустой submit; реальное перемещение только isolated stock pair, затем обратное перемещение как recovery.

### PROD-PLACEHOLDER-001 — инвентаризация

- `/app/ff/inventory`: зафиксировать полный экран и доступные действия. Если только `Раздел в разработке`, отметить процесс `GAP`, не visual defect.

## Seller portal — выполнять только разрешённой seller-role credential

В ходе прогона оркестратор получил разрешённый seller staging access и выполнил stable route batch. Значения credential не раскрываются; создавать/сбрасывать seller password запрещено.

- `PROD-SELLER-DOC-001` `/seller/documents`: тип/сортировка, создать inbound draft, создать MP draft, акт корректировки, открыть строку, reload/failure.
- `PROD-SELLER-INB-001` `/seller/inbound/new` и `/seller/inbound/:id`: date/boxes, add products, quantities, delete, save draft, submit warehouse, reload/failure.
- `PROD-SELLER-PROD-001` `/seller/products`: sync products (только isolated), FBS toggles (не менять shared), pagination, ТЗ dialog.
- `PROD-SELLER-HS-001` `/seller/honest-sign`: открыть прямым пунктом `Честный знак` в актуальном seller sidebar; проверить переходы к остаткам/браку/загрузке и отсутствие чужих seller data.
- `PROD-SELLER-SET-001` `/seller/settings`: status cards only. Credential dialogs and secret inputs are forbidden.
- `PROD-SELLER-NOTIF-001` `/seller/notifications`: bell, mark one/read-all only isolated notifications, reload.

## Что вернуть продуктовому агенту

1. Абсолютные пути всех screenshots.
2. Для каждого scenario: фактический URL после клика, viewport, роль, test object label без секретов, выполненное действие, status `PASS|FAIL|BLOCKED_*|N/A`.
3. Для mutation: до/после ID в приватной staging log заметке оркестратора и доказательство cleanup/recovery; в продуктовый отчёт передавать только безопасный alias.
4. Network/API error text можно пересказать, но не сохранять Authorization/cookies/request headers.
