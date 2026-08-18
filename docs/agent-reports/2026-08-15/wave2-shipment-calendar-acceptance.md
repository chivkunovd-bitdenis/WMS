# Wave2 shipment calendar acceptance

Дата приёмки: 2026-08-15  
Ветка/worktree: `iteration/wms-wave2-shipment-calendar-20260815` / `/Users/deniscivkunov/Projects/WMS/.worktrees/wave2-shipment-calendar-20260815`  
Вердикт: `PRODUCT_BROWSER_APPROVED` по CAL-01, CAL-02, CAL-03, NAV-01. Stop-находок нет.

## Способ проверки

Проверка выполнена в настоящем внешнем окне ОС: Google Chrome `151.0.7922.138`, открытый через macOS `open -na "Google Chrome"` с отдельным профилем и `--remote-debugging-port=9223`. Управление: CDP mouse events и ввод в видимом окне Chrome; Playwright/headless/API для UI-проверок не использовались. API/DB применялись только для setup данных.

Локальные URL:

- FF/seller frontend: `http://127.0.0.1:5177/`
- API: `http://127.0.0.1:19080`
- База setup: отдельная SQLite `backend/wave2-shipment-calendar-acceptance-1786805600.sqlite` (не артефакт приёмки, в commit не включается).

## Setup данных

Создан test tenant `CAL Acceptance FF 1165214000`, FF admin `cal-accept-ff-1165214000@example.com`, seller `CAL Seller 1165214000`, склад-направление `Москва / Коледино`, товар `Product cal-accept-1165214000`.

Для проверки отсечки tenant settings сначала выставлены в `16:00`. Через backend-сервис созданы два WB FBS-заказа и две FBS supply:

- `CAL Before cutoff`: заказ создан `2026-08-15 11:30 UTC` (`14:30 МСК`), planned shipment date = `2026-08-15`.
- `CAL After cutoff`: заказ создан `2026-08-15 14:30 UTC` (`17:30 МСК`, после отсечки `16:00`), planned shipment date = `2026-08-16`.

Для seller-раздела `Сегодня / Завтра` созданы две seller inbound-заявки с плановыми датами `2026-08-15` и `2026-08-16`, по одной строке на `2 шт` и `4 шт`.

## Проверенные критерии

CAL-01 принят. На FF dashboard видна месячная календарная сетка `август 2026 г.` с числами дней. В датах `15` и `16` отображаются строки FBS-отгрузок: `Москва / Коледино`, `1 коробов · FBS`. Старые dashboard-блоки приёмки/отгрузок не видны на этом экране.

CAL-02 принят. Клик по строке FBS на `16.08.2026` открыл workspace `CAL After cutoff`; в шапке workspace видны `Склад WMS: Москва / Коледино`, `Маршрут: Склад / СЦ`, поле `Дата отгрузки` со значением `16.08.2026`, состав поставки и 1 заказ.

CAL-03 принят. В настройках FF виден блок `Время отсечки FBS`. До UI-редактирования в поле было `16:00`; через видимый Chrome значение изменено на `16:30`, нажата кнопка `Сохранить`, UI показал `Время отсечки FBS сохранено`.

Правило после отсечки принято. При setup с отсечкой `16:00` заказ `CAL After cutoff`, созданный в `17:30 МСК` 15 августа 2026, автоматически получил planned shipment date `2026-08-16`; это подтверждено backend-сервисом и затем живым UI: строка находится в календарной ячейке `16`, а workspace показывает дату `16.08.2026`.

Seller-раздел принят. В seller portal на экране `Документы` виден блок `Сегодня / Завтра` с колонками `Сегодня` и `Завтра`. В `Сегодня` показана `Поставка` на `Москва / Коледино · 1 строк · 2 шт`, в `Завтра` показана `Поставка` на `Москва / Коледино · 1 строк · 4 шт`.

NAV-01 принят. В FF sidebar видимый порядок разделов:

`Приёмка на FF -> Сортировка -> FBS -> Отгрузки -> Упаковка -> Ячейки -> Селлеры -> Каталог -> Честный знак -> Календарь отгрузок -> Настройки`

Раздел `Календарь отгрузок` находится в нижней группе перед `Настройки`; `Приёмка на FF` и `Сортировка` находятся сверху перед FBS.

## 6a audit видимых элементов

На FF calendar screen:

- `Календарь отгрузок`, переключатели месяца, подписи дней недели, числа дней, календарная сетка, FBS-строки: CAL-01.
- FF sidebar order and labels: NAV-01.
- Topbar email, notification bell, `Выйти`, app frame/logo: существующая базовая задача shell/auth (`TC-S15-001`, `TC-S02-001`).

На FBS workspace after cutoff:

- Поле `Дата отгрузки`, кнопки `Сохранить`/`Очистить`: CAL-02.
- Название supply, seller, WB number, склад WMS, маршрут, прогресс, вкладки состава/подбора/упаковки/коробов, таблица заказа, кнопки печати/начала работы: существующий FBS workspace/operator flow.
- Sidebar/topbar behind dialog: NAV-01 + базовый shell.

На FF settings:

- Блок `Время отсечки FBS`, time input, `Сохранить`, `Очистить`, success message: CAL-03.
- Блоки `Склад`, `Адресное хранение`, `Раздельная печать ЧЗ и ШК ВБ`, staff/settings shell: существующие базовые настройки FF, не новая CAL/NAV-функция.
- Sidebar/topbar: NAV-01 + базовый shell.

На seller documents:

- Блок `Сегодня / Завтра`, колонки `Сегодня`/`Завтра`, seller-visible document cards: CAL-смежный seller visibility criterion for shipment/date summary.
- Кнопки создания документов, фильтры, таблица документов: существующий seller documents flow.
- Seller sidebar/topbar/logout: существующий seller shell/auth.

Придуманных новых UI-элементов, не относящихся к CAL-01/CAL-02/CAL-03/NAV-01 или существующим базовым задачам, не обнаружено.

## Evidence

- `assets/01-ff-calendar-grid-fbs-rows.png` — FF calendar grid with FBS rows on 15/16.
- `assets/02-fbs-workspace-after-cutoff-date.png` — clicked after-cutoff FBS row, workspace date `16.08.2026`.
- `assets/03-ff-settings-fbs-cutoff-visible.png` — cutoff setting visible before edit.
- `assets/04-ff-settings-fbs-cutoff-saved.png` — cutoff saved from UI.
- `assets/05-ff-nav-order-dashboard-bottom.png` — FF sidebar order with calendar/settings bottom group.
- `assets/06-seller-today-tomorrow-section.png` — seller `Сегодня / Завтра`.
- `assets/07-os-visible-chrome-seller.png` — macOS screenshot proving visible external Chrome window.
- `assets/live-browser-evidence.json` — browser/user-agent, clicked rows, extracted visible text.

## Technical verification

- Backend targeted test: `DATABASE_URL=sqlite+aiosqlite:///.../pytest-cal-accept-*.sqlite E2E_MOCK_WB_MARKETPLACE_SUPPLIES=1 pytest tests/test_fbs_supply_from_orders.py::test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` -> passed.
- Frontend build: `npm run build` -> passed. Vite emitted only the existing large chunk warning.

## Findings

Stop: нет.

Тормоз: нет.

Хвост: нет для acceptance. Временные локальные runtime-артефакты `.chrome-cal-acceptance/` и `backend/wave2-shipment-calendar-acceptance-1786805600.sqlite` не включены в commit, потому что это профиль Chrome и setup DB, а не приёмочные артефакты.
