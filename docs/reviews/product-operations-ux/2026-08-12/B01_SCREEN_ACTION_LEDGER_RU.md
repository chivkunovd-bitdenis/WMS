# Батч 01. Screen/action ledger

## Как читать

`Screen reachability` отвечает только «экран действительно открылся и видим». `Product-process verdict` отвечает «пользователь понимает, где он, что делать дальше и может безопасно передать работу». PASS по reachability не переносится на workflow следующих батчей. Для каждого выполненного пункта указан реальный screenshot. Empty state не используется как populated proof.

| ID | Модуль / route / роль / физический контекст | Действие в Browser и evidence | Ожидаемый операторский результат | Фактический результат, friction/error/recovery | Product-process verdict / severity / минимальное исправление / связь |
|---|---|---|---|---|---|
| B01-001 | Auth `/`, admin, начало смены | Открыт root при существующей synthetic session. `evidence/b01/b01-001-ff-login-1280x720.png` | Пока профиль загружается, одна понятная loading-сцена | Видно «Загрузка профиля…», без наложения login/register; текст упоминает Vite/API/docker — инженерный язык | `PASS_WITH_FRICTION` P2. Убрать инфраструктурную подсказку; далее B01-002 |
| B01-002 | Dashboard `/app/ff/dashboard`, admin, план смены, empty | Дождались profile. `b01-002` | Роль, организация, план, следующий шаг | Меню/роль/logout видны; обе таблицы empty; календарь ниже fold; есть `submitted` | `PASS_WITH_FRICTION` P1. Русский статус и приоритет текущей недели; populated отдельно B01-027 |
| B01-003 | Dashboard admin, полный экран 1280 | Full-page screenshot. `b01-003` | Весь план доступен прокруткой без горизонтальной потери | Документ 1280 px по ширине, 1288 px по высоте; календарь и CTA доступны ниже | `PASS_WITH_FRICTION` P2. Сократить первый экран; связь B01-004 |
| B01-004 | Dashboard calendar, admin | Нажата «Предыдущая неделя». `b01-004` | Явно меняется период | Период стал 03–09.08.2026 | `PASS` S0. Далее reload B01-005 |
| B01-005 | Dashboard reload, admin | Reload после смены недели. `b01-005` | Экран восстанавливается предсказуемо | Route сохранился; период вернулся к текущей неделе | `PASS` S0. Неделя — локальный view state; далее B01-006 |
| B01-006 | Dashboard admin, 1920×1080 DPR1 | Изменён viewport. `b01-006` | Ничего не обрезано, основные блоки видны | Ширина без overflow; календарь виден, низ страницы всё ещё ниже viewport; `submitted` остаётся | `PASS_WITH_FRICTION` P1. Русский статус; далее nav |
| B01-007 | FF menu `/app/ff/mp-shipments`, admin, dispatch | Клик «Отгрузки на МП». `b01-007` | Active nav и понятное назначение | Active виден, populated список и CTA видны | `PASS_WITH_FRICTION` P2. Только reachability; workflow не оценён; далее B01-008 |
| B01-008 | FF menu `/app/ff/fbs`, admin | Клик FBS. `b01-008` | Active nav, без регрессии baseline | Active, основные tabs/CTA видны, empty orders | `PASS` S0 reachability only. FBS workflow вне B01; далее B01-009 |
| B01-009 | FF menu `/app/ff/reception`, admin, входящие короба | Клик «Приёмка». `b01-009` | Очередь и active nav | Active, одна synthetic строка | `PASS` S0 reachability only; процесс B03 |
| B01-010 | FF menu `/app/ff/sorting`, admin, товар после пересчёта | Клик «Сортировка». `b01-010` | Active nav, понятный empty state | Active; «всё разложено по ячейкам» и пояснение зоны | `PASS` S0 reachability only; процесс B04 |
| B01-011 | FF menu `/app/ff/packaging`, admin | Клик «Упаковка». `b01-011` | Active nav и главный CTA | Active, «Создать задание» виден, empty list | `PASS` S0 reachability only; процесс B06/B08 |
| B01-012 | FF menu `/app/catalog`, admin, адресное хранение | Клик «Ячейки». `b01-012` | Active nav, склад и ячейки | Active; populated склад и ячейки, CTA видны | `PASS` S0 reachability only; процесс B04 |
| B01-013 | FF menu `/app/ff/sellers`, admin | Клик «Селлеры». `b01-013` | Active nav, список и создание | Active; два synthetic селлера, форма видна | `PASS` S0 reachability; создание отдельно B01-031 |
| B01-014 | FF menu `/app/ff/products`, admin, каталог склада | Клик «Каталог». `b01-014` | Действия и таблица целиком доступны на 1280 | Документ шириной 1727 при viewport 1280; правые колонки/действия обрезаны | `FAIL_UX` P1. Сжать/закрепить действия и явный table scroll; процесс B02/B05 |
| B01-015 | FF menu `/app/ff/inventory`, admin, инвентаризация | Клик «Инвентаризация». `b01-015` | Рабочий раздел или недоступность заранее | Рабочий пункт ведёт на «Раздел в разработке» | `FAIL_PROCESS` P1. Убрать/disable с альтернативой; процесс B05 |
| B01-016 | FF menu `/app/ff/honest-sign`, admin | Клик «Честный знак». `b01-016` | Active nav и понятный empty state | Active, KPI и CTA видны, empty codes | `PASS` S0 reachability only; процесс B08 |
| B01-017 | FF menu `/app/ff/settings`, admin | Клик «Настройки». `b01-017` | Active nav, account/staff controls | Active; storage switches, staff section; часть ниже fold | `PASS` S0 reachability; staff B01-057 |
| B01-018 | Notifications popover, admin | Клик bell. `b01-018` | Короткий список и переход ко всем | Два уведомления и «Показать все» | `PASS` S0; далее B01-019 |
| B01-019 | `/app/ff/notifications`, admin | «Показать все». `b01-019` | Полный список и ясная ориентация | Список открылся, но ни один sidebar item не active | `PASS_WITH_FRICTION` P2. Active bell/breadcrumb; далее history |
| B01-020 | Browser Back notifications→settings, admin | Back. `b01-020` | Вернуться в прежний раздел | Settings и active nav восстановлены | `PASS` S0; далее B01-021 |
| B01-021 | Browser Forward settings→notifications, admin | Forward. `b01-021` | Вернуться к уведомлениям | Route/список восстановлены; active sidebar отсутствует | `PASS_WITH_FRICTION` P2. Ориентация notifications; далее B01-022 |
| B01-022 | Notifications reload, admin | Reload. `b01-022` | Route/data сохраняются | Сохранились; active sidebar отсутствует | `PASS_WITH_FRICTION` P2. Далее logout |
| B01-023 | Logout FF, admin | Нажат «Выйти», поля затем очищены перед screenshot. `b01-023` | Публичный root без auth context | Login виден, но URL остаётся `/app/ff/notifications`; браузер до очистки имел оба поля непустыми | `PASS_WITH_FRICTION` P2. Replace на `/`; далее B01-024 |
| B01-024 | FF registration mode | «Регистрация организации». `b01-024` | Понятно, что это первый admin | Организация/email/password и объяснение видны | `PASS` S0. Submit новой организации не нужен для B01 |
| B01-025 | FF login invalid syntax | Невалидный домен, submit, поля очищены. `b01-025` | Ясная ошибка, доступ не выдан, можно исправить | Подробная validation error; форма сохранена | `PASS` S0. Recovery B01-026 |
| B01-026 | FF login recovery, admin | Введены synthetic staging credentials. `b01-026` | Успешный role landing | Сессия восстановилась на текущем protected route notifications | `PASS` S0. От корня отдельно B01-056 |
| B01-027 | Dashboard populated, admin, диспетчер смены | Вход существующим staging admin. `b01-027` | Текущие работы и очевидный переход | Пять входящих Denmarcs, outbound empty, календарь ниже; список старых дат | `PASS_WITH_FRICTION` P2. Текущая неделя/исключения первыми; row B01-028 |
| B01-028 | Dashboard populated row action, admin | Клик первой строки. `b01-028` | Видимое и keyboard-доступное «Открыть» | Точный outcome: открылся диалог «Приёмка №000005», статус «В сортировке», 2 товара, короба, распределение по ячейкам. Строка была `<tr>` pointer без role/tabindex/aria-label | `FAIL_UX` P1. Настоящая link/button + focus; далее B01-029 |
| B01-029 | Dashboard document dialog close, admin | Верхняя «Закрыть». `b01-029` | Без потери dashboard | Диалог закрылся, dashboard восстановлен | `PASS` S0; далее CTA B01-030 |
| B01-030 | Dashboard CTA «Открыть Селлеры», admin | Клик CTA. `b01-030` | Перейти в создание клиента | `/sellers`, active nav «Селлеры» | `PASS` S0; вход в процесс B01-031 |
| B01-031 | Create synthetic seller, admin | Заполнены name/email, «Добавить». `b01-031` | Success и точная инструкция handoff селлеру | Success содержит email, `/seller/`, первый вход | `PASS` S0; durable read-back B01-032 |
| B01-032 | Seller fixture reload read-back, admin | Reload. `b01-032` | Созданный seller остаётся | Одна matching synthetic row | `PASS` S0; handoff в seller auth B01-033 |
| B01-033 | Seller public login `/seller/`, первый вход | Переход из FF portal; screenshot. `b01-033` | Пустой login и инструкция | Browser autofill подставил admin email/password; инструкция говорит оставить пароль пустым | `PASS_WITH_FRICTION` P1. Отдельный first-login CTA; failure B01-034 |
| B01-034 | Seller first-login submit с автоподстановкой | Email synthetic seller, попытка очистить/submit. `b01-034` | Passwordless handshake | Получено «Неверный email или пароль»; пароль был непустым | `FAIL_PROCESS` P1. Исключить пустой password как gesture; recovery B01-035 |
| B01-035 | Seller first-login recovery | Focus, Meta+A, Backspace, submit. `b01-035` | Открыть setup | Setup «Установите пароль» открылся | `PASS_WITH_FRICTION` P1. Recovery требует знания browser behavior; далее cancel B01-036 |
| B01-036 | Seller setup cancel | «Назад ко входу». `b01-036` | Безопасно вернуться | Login восстановлен; autofill снова требует очистки | `PASS` S0 для cancel; далее повтор setup |
| B01-037 | Seller setup mismatch error | Разные значения, submit. `b01-037` | Ясная ошибка без потери setup | «Пароли не совпадают», поля доступны | `PASS` S0; далее correct submit |
| B01-038 | Seller first landing `/seller/documents`, 1280 | Correct password setup. `b01-038` | Seller context на русском и следующий шаг | Documents/CTA видны; шапка показывает `fulfillment_seller`, нет бренда/ФФ | `FAIL_UX` P1. Человеческий role+seller context; empty list only |
| B01-039 | Seller landing 1920×1080 DPR1 | Resize. `b01-039` | Ничего не обрезано | CTA видны, горизонтального overflow нет; role code остаётся | `FAIL_UX` P1. Та же проблема контекста; B01-040 cross-check |
| B01-040 | Seller landing 1280 cross-check | Resize обратно. `b01-040` | CTA/filters/table видны | Все три CTA видны, no document overflow | `FAIL_UX` P1 только role context; populated row B01-065 |
| B01-041 | Seller `/products`, seller, ассортимент | Клик «Товары». `b01-041` | Active nav, основные колонки/действия видны | Active; empty; ширина документа 1727 на 1280, правые колонки обрезаны | `FAIL_UX` P1. Responsive table/actions; populated B01-066 |
| B01-042 | Seller `/honest-sign` | Клик «Честный знак». `b01-042` | Active nav и empty guidance | Active, KPI/CTA, empty codes | `PASS` S0 reachability only; workflow B08 |
| B01-043 | Seller `/settings` | Клик «Настройки». `b01-043` | Active nav и понятное состояние integrations | Active; WB key not added, ЧЗ summary | `PASS` S0 reachability only; keys не трогались |
| B01-044 | Seller `/documents`, empty | Клик «Документы». `b01-044` | Active nav, CTA и honest empty state | Active, три CTA, filters, empty row | `PASS` S0 для empty/reachability; populated B01-065 |
| B01-045 | Seller notifications popover | Bell. `b01-045` | Empty popover и «Показать все» | Открылось корректно | `PASS` S0; далее B01-046 |
| B01-046 | Seller `/notifications` | «Показать все». `b01-046` | Empty list и ясная ориентация | «Нет уведомлений», sidebar no active | `PASS_WITH_FRICTION` P2. Active bell/breadcrumb |
| B01-047 | Seller Browser Back | Back notifications→documents. `b01-047` | Documents восстановлены | URL и active nav восстановлены | `PASS` S0; далее B01-048 |
| B01-048 | Seller Browser Forward | Forward. `b01-048` | Notifications восстановлены | Route restored, no active sidebar | `PASS_WITH_FRICTION` P2. Ориентация |
| B01-049 | Seller notifications reload | Reload. `b01-049` | Route/empty state сохраняются | Сохранились, no active sidebar | `PASS_WITH_FRICTION` P2 |
| B01-050 | Seller direct FF URL `/app/ff/dashboard` | Direct goto при seller session. `b01-050` | Не попасть в FF shell/tenant | Показан публичный FF login, authenticated FF shell отсутствует | `PASS` S0. Разделение порталов работает |
| B01-051 | Seller back после FF URL | Browser Back. `b01-051` | Вернуться в seller session | Seller notifications восстановлены | `PASS` S0 |
| B01-052 | Seller unknown route | `/seller/no-such-route-b01`. `b01-052` | Без dead end, понятный default | Redirect/replace на `/seller/documents`, active Documents | `PASS` S0 |
| B01-053 | Seller repeat login wrong password | Logout, wrong password, поля очищены для evidence. `b01-053` | Clear error, no access | «Неверный email или пароль.» | `PASS` S0; recovery B01-054 |
| B01-054 | Seller repeat login recovery | Correct synthetic password. `b01-054` | Default seller landing | `/seller/documents`, active Documents | `PASS` S0 |
| B01-055 | FF login wrong credentials valid format | Wrong account/password, fields очищены. `b01-055` | Clear generic error, no leakage | «Неверный email или пароль.» | `PASS` S0; recovery B01-056 |
| B01-056 | FF root login role landing | Correct admin login from root. `b01-056` | Default `/dashboard` | `/app/ff/dashboard`, active Dashboard, populated inbound | `PASS_WITH_FRICTION` P1. Landing correct, `submitted` remains |
| B01-057 | Create synthetic FF staff + permissions | Settings: create staff, enable reception+MP. `b01-057` | Success and explicit permissions | Row created; permission clicks visible | `PASS` S0; reload B01-058 |
| B01-058 | Staff permission reload read-back | Reload settings. `b01-058` | Account/permissions durable | One synthetic row; both permissions checked after reload; table width 1788 at 1280 | `PASS_WITH_FRICTION` P2. Admin settings table needs local horizontal affordance; first login B01-059 |
| B01-059 | FF staff first-login setup | Logout, blank password handshake. `b01-059` | Setup screen | Setup opened and correct values accepted | `PASS` S0; landing B01-060 |
| B01-060 | FF staff role landing | Correct setup submit. `b01-060` | Russian role, only allowed menu, actionable work | Topbar «сотрудник»; Dashboard, MP, Reception, Sorting only; dashboard populated in captured state | `PASS` S0 for landing/menu; worklists B01-063/064 |
| B01-061 | Staff direct `/app/ff/sellers` | Direct goto. `b01-061` | Forbidden or safe explanation, no admin mutation | Screen reachable, no rows, clear «доступно только администратору», no create form | `PASS_WITH_FRICTION` P2. Prefer explicit 403/return, not admin screen shell |
| B01-062 | Staff direct `/app/ff/settings` | Direct goto. `b01-062` | Protected route not accessible | Replaced by `/app/ff/dashboard` | `PASS` S0 |
| B01-063 | Staff `/app/ff/reception`, permissioned operator | Menu click. `b01-063` | Populated worklist with Russian physical status | Denmarcs row visible; status raw `receiving` | `FAIL_UX` P1. Русский status map «Идёт приёмка»; next role sorting |
| B01-064 | Staff `/app/ff/mp-shipments`, permissioned operator | Menu click. `b01-064` | Permission gives coherent view/work or coherent denial | Raw `forbidden` вместе с seller selector, create CTA и existing documents; core-flow impossibility и межтенантная утечка в B01 не доказаны | `FAIL_PROCESS` P1. Align dependent API scope/CTA with permission before operational use |
| B01-065 | Seller documents populated row/action | Нужной synthetic строки нет; empty B01-044 | Открыть собственный документ, reload/read-back | Empty state не доказывает populated action | `BLOCKED_FIXTURE` P1. Нужен безопасный seller document fixture без реальных WB данных |
| B01-066 | Seller products populated row/action | Нужного synthetic товара нет; empty B01-041 | Проверить row/action/overflow с данными | Empty state only | `BLOCKED_FIXTURE` P1. Нужен synthetic product fixture |
| B01-067 | Admin dashboard populated outbound row | Таблица empty в B01-027 | Клик строки открывает конкретную отгрузку и следующий шаг | Нет безопасной строки в требуемом dashboard status | `BLOCKED_FIXTURE` P1. Нужна synthetic submitted MP shipment |
| B01-068 | Double-click создающих CTA | Не выполнялось: create shipment/act/sync вне B01 и меняет данные | Идемпотентность/защита от повтора | Не проверено безопасно в батче ориентации | `NOT_RUN` P1. Перенести в соответствующие B02/B06/B07/B08 |
| B01-069 | Profile slow/error recovery | Наблюдалась обычная короткая loading B01-001, искусственная сеть не менялась | Длительная задержка, retry/clear recovery | Controlled slow/error fixture отсутствует | `NOT_RUN` P2. Нужен безопасный network fixture; ordinary loading PASS_WITH_FRICTION в B01-001 |
| B01-070 | Logout/account context at 1920 seller/admin | Topbars проверены B01-006/B01-039 | Email, role, logout полностью видны | Все видны; seller role технический, admin role русский | `PASS_WITH_FRICTION` P1. Seller human context; связь findings F02 |

## Coverage и verdict counts

- Ledger rows: **70**.
- Реально сохранённых screenshots: **64**.
- Уникальные routes, фактически открытые в Browser: **22** (публичные root/portal routes учтены отдельно от protected routes).
- Основные menu routes: admin **12**, seller **4**, permissioned staff **4** (частично совпадают с admin routes).
- Проверены: main nav active state, notification popover/list, back/forward/reload, logout, wrong-login recovery, first-login setup/cancel/mismatch, direct/unknown URLs, два viewport.

Итоговые статусы ledger:

- `PASS`: **36**
- `PASS_WITH_FRICTION`: **19**
- `FAIL_PROCESS`: **3**
- `FAIL_UX`: **7**
- `BLOCKED_FIXTURE`: **3**
- `NOT_RUN`: **2**
- `N/A`: **0**

Screen reachability: большинство advertised routes доступны. Product-process verdict: ориентационный аудит закрыт, но выявлены P1 staff permission/API conflict, first-login trap и три явных fixture gaps. Предложение gate: `ACCEPTED_WITH_BLOCKED_FIXTURES`; в формальном трёхзначном шаблоне — `ACCEPTED` с сохранёнными строками `BLOCKED_FIXTURE`.
