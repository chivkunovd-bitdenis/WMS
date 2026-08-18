# Батч 03. Исполнимый Browser-чеклист приёмки

Статус до живого действия — `PLANNED`. Каждая выполненная строка позже переносится в screen/action ledger с отдельным verdict и screenshot. Статический код не превращает `PLANNED` в `PASS`.

## A. Вход, очередь и доказательство документа

| ID | Действие | Обязательное доказательство | Статус |
|---|---|---|---|
| B03-C001 | Подключить in-app Browser, открыть Railway staging при viewport 1280×720 | Видимый route и измеренные CSS metrics | PLANNED |
| B03-C002 | Войти/восстановить fulfillment admin session штатным UI | FF shell, admin context, без secret в evidence | PLANNED |
| B03-C003 | Открыть «Приёмка» через sidebar | Active nav, populated queue | PLANNED |
| B03-C004 | Зафиксировать queue целиком до открытия строки | Колонки, статусы, seller/date/line_count, нет угадывания | PLANNED |
| B03-C005 | Проверить keyboard reachability строки (Tab/role/focus) | Видимый focus или доказанное отсутствие | PLANNED |
| B03-C006 | Найти кандидатов seller/date/2 lines и открыть только read-only | Candidate screenshots, без mutation | PLANNED |
| B03-C007 | Доказать exact detail: seller, 2 lines, A=3, B=2, boxes plan=2 | Один detail и sanitized request id | PLANNED |
| B03-C008 | Зафиксировать несовпадающих кандидатов и безопасно закрыть | Неизменённый queue/read-back | PLANNED |
| B03-C009 | Проверить Close → queue | Контекст и scroll/selection не потеряны | PLANNED |
| B03-C010 | Проверить Browser Back/Forward detail↔queue | Предсказуемый route/state | PLANNED |
| B03-C011 | Reload exact detail до mutation | Тот же номер/status/plan/lines | PLANNED |
| B03-C012 | Попытаться 1920×1080 только после установки и измерения exact CSS metrics/DPR1 | Screenshot либо `BLOCKED_ENV` | PLANNED |

## B. Начальное состояние и операторская читаемость

| ID | Действие | Обязательное доказательство | Статус |
|---|---|---|---|
| B03-C013 | Проверить, что все идентификаторы и следующий CTA помещаются на 1280 | Full visible detail + metrics | PLANNED |
| B03-C014 | Сопоставить товар name/SKU/ШК/размер/фото с планом | Две различимые строки | PLANNED |
| B03-C015 | Сопоставить `Заявлено` и исходное `Принято` | A=3/B=2 vs initial fact | PLANNED |
| B03-C016 | Проверить plan boxes=2 против фактических коробов/empty state | Видимый итог коробов | PLANNED |
| B03-C017 | Проверить верхний и панельный CTA завершения на дублирование/иерархию | Оба CTA или один очевидный CTA | PLANNED |
| B03-C018 | Открыть/закрыть печать накладной без подтверждения печати, если безопасно | Print preview или `BLOCKED_ENV`; no false PASS | PLANNED |

## C. Сканирование и ручной факт

| ID | Действие | Обязательное доказательство | Статус |
|---|---|---|---|
| B03-C019 | Отправить пустой скан/Enter | Никакой mutation, понятное disabled/validation | PLANNED |
| B03-C020 | Ввести неизвестный synthetic barcode и Enter | Русская error feedback, факт не изменён | PLANNED |
| B03-C021 | Reload после unknown scan | Исходный факт | PLANNED |
| B03-C022 | Сканировать валидный barcode A один раз клавишей Enter | A +1, focus готов к следующему скану | PLANNED |
| B03-C023 | Reload после valid scan | +1 сохранён | PLANNED |
| B03-C024 | Два быстрых одинаковых скана/двойной клик | Ровно два физических события либо защита от случайного click; точный outcome | PLANNED |
| B03-C025 | Reload после repeat | Durable точное значение | PLANNED |
| B03-C026 | Открыть ручную правку A и Cancel через повторный edit/blur strategy | Незавершённое значение не тихо сохранено | PLANNED |
| B03-C027 | Ввести отрицательное количество | Ясная ошибка, mutation отсутствует | PLANNED |
| B03-C028 | Ввести дробное количество | Ясная целочисленная validation, не молчаливое округление | PLANNED |
| B03-C029 | Ввести нечисловое/пустое значение | Ясная error/recovery | PLANNED |
| B03-C030 | Установить A=0 | Ноль сохранён, строка явно discrepancy | PLANNED |
| B03-C031 | Reload A=0 | Durable zero, не «не заполнено» | PLANNED |
| B03-C032 | Установить A выше плана | Overage сохранён и явно отмечен | PLANNED |
| B03-C033 | Reload overage | Durable overage + warning | PLANNED |
| B03-C034 | Восстановить A=3 и B=2 | Обе match-state, нет discrepancy | PLANNED |
| B03-C035 | Reload exact match | A=3/B=2 durable | PLANNED |
| B03-C036 | Проверить Tab/Enter-путь между edit controls | Работа без точного mouse hit | PLANNED |

## D. Короба

| ID | Действие | Обязательное доказательство | Статус |
|---|---|---|---|
| B03-C037 | Создать один synthetic короб | Ровно одна новая box row, номер/ШК | PLANNED |
| B03-C038 | Double-click create box | Нет неожиданного второго короба либо точный duplicate outcome | PLANNED |
| B03-C039 | Reload boxes | Exact count/read-back | PLANNED |
| B03-C040 | Открыть «Наполнить» | Dialog с номером и двумя товарами | PLANNED |
| B03-C041 | Unknown scan внутри короба | Русская ошибка, состав не изменён | PLANNED |
| B03-C042 | Valid scan A внутри короба | A +1 в коробе и общем факте, без двойного учёта | PLANNED |
| B03-C043 | Reload/reopen box | Box composition durable, общий факт согласован | PLANNED |
| B03-C044 | Manual plus/minus/qty для B | Точный box qty и общий факт | PLANNED |
| B03-C045 | Попытка превышения/некорректного box qty | Error или явный discrepancy без silent failure | PLANNED |
| B03-C046 | Закрыть dialog крестиком и кнопкой | Оба пути сохраняют уже подтверждённые изменения одинаково | PLANNED |
| B03-C047 | Удалить пустой короб | Явный результат и reload read-back | PLANNED |
| B03-C048 | Попытаться удалить непустой короб | Защита/объяснение, состав не потерян | PLANNED |
| B03-C049 | Проверить box label/print controls без реальной печати при невозможности preview | Reachability отдельно от print success | PLANNED |
| B03-C050 | Восстановить итоговый факт A=3/B=2 без box double-count | Lines/box totals согласованы | PLANNED |

## E. Расхождения и завершение

| ID | Действие | Обязательное доказательство | Статус |
|---|---|---|---|
| B03-C051 | Создать controlled underage B=1 | Красная/предупреждающая строка и общий hint | PLANNED |
| B03-C052 | Нажать «Завершить» при underage | Confirmation с понятным последствием | PLANNED |
| B03-C053 | Cancel confirmation | Detail остаётся receiving, факт B=1 | PLANNED |
| B03-C054 | Reload после Cancel | Ни stock, ни status transition не возникли | PLANNED |
| B03-C055 | Восстановить exact A=3/B=2 | Warning исчез; match state | PLANNED |
| B03-C056 | Нажать верхний CTA и быстро повторить/double-click | Ровно один completion; точный disabled/transition outcome | PLANNED |
| B03-C057 | Reload completed detail | Status «В сортировке», fact locked, success handoff | PLANNED |
| B03-C058 | Проверить повторное завершение | CTA отсутствует/недоступен; no duplicate stock | PLANNED |
| B03-C059 | Проверить locked box/detail after completion | Нет неявной edit mutation | PLANNED |
| B03-C060 | Проверить «Редактировать» reachability и confirmation semantics, не оставляя reopened state | Exact safe outcome или `NOT_RUN_SAFETY` | PLANNED |

## F. Handoff в сортировку и stock semantics

| ID | Действие | Обязательное доказательство | Статус |
|---|---|---|---|
| B03-C061 | Закрыть completed detail и перечитать очередь «Приёмка» | Exact document отсутствует | PLANNED |
| B03-C062 | Открыть «Сортировка» через sidebar | Matching seller/date/2 lines row | PLANNED |
| B03-C063 | Проверить remaining qty | 5 units при exact A=3/B=2 | PLANNED |
| B03-C064 | Открыть matching sorting detail read-only | Тот же human number, two lines, accepted 3/2 | PLANNED |
| B03-C065 | Не выполнять distribution; закрыть detail/reload | B04 fixture сохранён | PLANNED |
| B03-C066 | Проверить FF product read-back для A/B | В сортировке=3/2, total includes 3/2, available excludes sorting | PLANNED |
| B03-C067 | Reload product read-back | Stock semantics durable | PLANNED |
| B03-C068 | Проверить seller product read-back только при сохранённой safe session | On-hand includes accepted; available semantics не искажены | PLANNED |

## G. Evidence и gate

| ID | Действие | Обязательное доказательство | Статус |
|---|---|---|---|
| B03-C069 | Сохранить sanitized state log | request id, number, metrics, facts, transitions; no secrets | PLANNED |
| B03-C070 | Лично открыть каждый PNG через `view_image` | Один visual verdict на каждый кадр | PLANNED |
| B03-C071 | Свести ledger без переносов verdict из кода | Все 71 ID имеют конечный status | PLANNED |
| B03-C072 | Findings только evidence-backed, с минимальным исправлением | Нет оверинжиниринга | PLANNED |
| B03-C073 | Handoff сохранить B04 fixture и stop boundaries | Exact final state и open gaps | PLANNED |

Всего: **73 контрольных пункта**. Ветка/commit/deploy не меняются этим батчем; B03 создаёт только review evidence и документы, а commit выполняет оркестратор.
