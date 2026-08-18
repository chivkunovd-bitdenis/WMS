# Батч 02. Screen/action ledger seller-процесса

## Правила чтения

Ledger закрывает все 63 пункта `B02_EXECUTION_CHECKLIST_RU.md` ровно по одному. Здесь `FRICTION` соответствует контрактному `PASS_WITH_FRICTION`: задачу можно продолжить, но интерфейс создаёт лишнюю работу или риск. `NOT_RUN` не является положительным verdict. Кадры `015`, `016`, `031`, `034`, `038`, `040` не используются как доказательство устойчивого состояния: они подтверждают только оговорённый transitional/loading risk. `008` не является 1920×1080 evidence.

| ID | Фактическое действие / результат | Evidence / source | Статус | Product verdict для реального сотрудника |
|---|---|---|---|---|
| B02-C001 | Подключён настоящий in-app Browser и открыт staging. | `evidence/b02/001–041`; visual slices A–C | PASS | Проверка выполнена через живой интерфейс, а не по коду или HTTP. |
| B02-C002 | Isolated synthetic seller вошёл в `/seller/documents`; чужие строки в исходном empty-state не показаны. | `b02-001-seller-documents-empty-1280x720.png` | PASS | Seller-контекст достижим; человеческое название кабинета при этом не показано. |
| B02-C003 | Admin открыл штатный manual-create dialog без WB sync. | `b02-002-admin-product-dialog-empty-1280x720.png` | PASS | Ролевая передача admin→seller начинается в правильном интерфейсе. |
| B02-C004 | Пустой submit остановлен native required-validation для seller/name/SKU; mutation не возникла. | `b02-002-admin-product-dialog-empty-1280x720.png`; Browser runtime из slice A | FRICTION | Защита есть, но отдельный кадр с текстом каждой ошибки не снят, а различие двух артикулов не объяснено. |
| B02-C005 | Cancel заполненной формы создания товара отдельно не воспроизведён. | Нет собственного screenshot до/после | NOT_RUN | Нельзя утверждать, что partially filled product не создаётся и не сохраняется. |
| B02-C006 | Double-click Create для SKU-A дал ровно одну строку. | `b02-003-admin-product-a-filled-1280x720.png`, `b02-004-admin-product-a-readback-1280x720.png`; Browser runtime | PASS | Повторный клик не создал видимый дубль. |
| B02-C007 | SKU-A сохранился и затем появился у seller после смены route; отдельный admin reload-capture не снят. | `b02-004-admin-product-a-readback-1280x720.png`, `b02-007-seller-products-populated-1280x720.png` | FRICTION | Durable role handoff подтверждён косвенным read-back, но точная admin reload-проверка неполна. |
| B02-C008 | Повтор SKU-A отклонён ясной ошибкой; отдельный duplicate-barcode case не выполнен. | `b02-005-admin-product-duplicate-sku-error-1280x720.png` | FRICTION | SKU защищён хорошо; нельзя переносить этот verdict на ШК. |
| B02-C009 | Создан второй synthetic SKU-B и прочитан обратно. | `b02-006-admin-product-b-readback-1280x720.png`, `b02-007-seller-products-populated-1280x720.png` | PASS | Два товара дают рабочий fixture для выбора и сверки. |
| B02-C010 | Seller видит оба своих товара с идентификаторами и нулевым stock на 1280×720. Правые колонки и действия обрезаны. | `b02-007-seller-products-populated-1280x720.png` | FAIL_UX | Ключевое действие и часть остатка находятся вне видимой области; плохо обученный пользователь не понимает, что экран продолжается вправо. |
| B02-C011 | Валидный 1920×1080 DPR1 прогон не получен. | `b02-008-seller-products-populated-1920x1080.png`; runtime: фактически 1280×720, DPR2 | NOT_RUN | Имя файла не считается доказательством viewport. |
| B02-C012 | При отсутствии WB key Products показывает активный и визуально главный sync CTA, тогда как Settings показывает sync disabled. Sync не нажимался. | `b02-007...png`, `b02-032-products-after-submit-second-readback-1280x720.png`, `b02-039-seller-settings-overview-1280x720.png` | FAIL_UX | Один и тот же credentialless state объяснён противоречиво и провоцирует бесполезный внешний шаг. |
| B02-C013 | FBS per-row/bulk controls инвентаризированы без переключения stock. | `b02-007...png`, `b02-032...png` | FRICTION | Граница безопасности соблюдена, но bulk CTA визуально сильнее локальной подготовки товара. |
| B02-C014 | ТЗ открыто, product identity/текст/marking видны; Cancel сохранил прежнее значение. | `b02-009-seller-packaging-task-open-1280x720.png`; Browser runtime | FRICTION | Передача инструкции ФФ логична, но непонятно, какую версию печатает соседняя кнопка. |
| B02-C015 | Новый safe text и marking flag сохранены; dialog закрылся после double-click. | `b02-010-seller-packaging-task-saved-1280x720.png`, `b02-011...readback...png`; Browser runtime | FRICTION | Один persisted outcome есть, но явный busy/«сохранено» feedback отсутствует. |
| B02-C016 | После reload/reopen новый текст и checkbox восстановлены. | `b02-011-seller-packaging-task-reload-readback-1280x720.png` | PASS | ФФ получит durable инструкцию, а не только локальный draft. |
| B02-C017 | Cancel проверен; wrong/empty ТЗ отдельными cases не проверялись. | `b02-009...png`; Browser runtime | FRICTION | Отмена предсказуема, но трактовка пустой инструкции остаётся непроверенной. |
| B02-C018 | Print не запускался: безопасный preview/диалог не был отделён от внешней печати. | CTA видна на `b02-009...png`, собственного outcome нет | NOT_RUN | Нельзя утверждать, что печатается сохранённая версия и что пользователь может безопасно отменить печать. |
| B02-C019 | Открытие `/seller/inbound/new` само создало draft до нажатия Save; ID/номер и Cancel/Delete отсутствуют. | `b02-012-seller-inbound-new-empty-1280x720.png` | FAIL_PROCESS | Простое посещение формы уже меняет данные и оставляет документ, о котором пользователь не знает. |
| B02-C020 | Reload literal `/seller/inbound/new` создал новый пустой draft и вывел пользователя из заполненного. | `b02-020-inbound-line-zero-reload-readback-1280x720.png`, финальный список `b02-041...png` | FAIL_PROCESS | Пользователь воспринимает это как потерю работы и размножает черновики. |
| B02-C021 | Past/empty/wrong date и recovery не проверены. | Нет собственного screenshot | NOT_RUN | Date-validation не получила verdict. |
| B02-C022 | Boxes=0 молча выключает submit; recovery до 2 и reload-readback работают. Negative/decimal/text не проверены. | `b02-023-inbound-boxes-zero-validation-1280x720.png`, `b02-024-inbound-boxes-two-reload-readback-1280x720.png` | FAIL_UX | Защита от передачи есть, но сотрудник не понимает причину блокировки. |
| B02-C023 | Picker открылся и содержит только два seller товара; отдельный cancel outcome не снят. | `b02-013-seller-inbound-product-picker-1280x720.png` | FRICTION | Выбор товара понятен, но допустимые количества не обозначены заранее. |
| B02-C024 | Qty `0/-2` закрыли picker без lines и без ошибки; decimal/text не проверены. | `b02-014-seller-inbound-picker-invalid-qty-1280x720.png`; Browser runtime | FAIL_UX | Система молча игнорирует работу пользователя и не даёт восстановиться в том же контексте. |
| B02-C025 | SKU-A=3 и SKU-B=2 добавлены в draft. | `b02-017-seller-inbound-picker-valid-quantities-1280x720.png`, `b02-022-recovered-two-line-draft-1280x720.png` | FRICTION | Состав формируется верно, но нет итога «2 позиции / 5 единиц». |
| B02-C026 | Повторное добавление SKU-A не имеет отдельного settled screenshot. | Нет собственного authoritative screenshot | NOT_RUN | Нельзя дать положительный verdict duplicate-line guard только по runtime-описанию. |
| B02-C027 | Inline qty=0 осталось в поле после blur без ошибки; durable save этого нуля не доказан, потому что reload `/new` открыл другой draft. | `b02-019-inbound-line-zero-after-blur-1280x720.png`, `b02-020...png` | FAIL_UX | Сотрудник видит физически бессмысленную строку и не знает, принята она системой или нет. |
| B02-C028 | Удаление строки произошло одним кликом без confirm/undo; reload подтвердил удаление, ручное re-add восстановило строку. | `b02-025...delete...png`, `b02-026...readback...png`, `b02-027...readded...png` | FAIL_UX | Случайный клик может незаметно убрать товар из передаваемой поставки. |
| B02-C029 | Save draft double-click не имеет settled authoritative before/after/read-back набора; `016` transitional. | `b02-016...png` исключён как invalid evidence | NOT_RUN | Нельзя подтвердить идемпотентность отдельной кнопки Save. |
| B02-C030 | Старый filled draft найден вручную; boxes=2 и lines пережили detail reload. | `b02-022...png`, `b02-024...png` | FRICTION | Данные durable, но recovery требует угадать нужную безымянную строку в списке. |
| B02-C031 | Browser back/forward для draft отдельно не проверены. | Нет собственного screenshot | NOT_RUN | Контекстный recovery по истории браузера не доказан. |
| B02-C032 | Invalid boxes=0 блокирует submit без объяснения; missing lines блокируют CTA. | `b02-012...png`, `b02-023...png` | FAIL_UX | Бизнес-guard есть, но интерфейс не говорит, что именно исправить. |
| B02-C033 | Double-click valid submit дал один `draft→submitted`; lines=2, stock по обоим товарам остался 0. | `b02-028-inbound-submit-doubleclick-result-1280x720.png`, `b02-032-products-after-submit-second-readback-1280x720.png`; runtime | FRICTION | Основная транзакция безопасна, но success-row не имеет номера и точного состава. |
| B02-C034 | Submitted detail пережил reload и заблокировал business fields; Save остался enabled, title всё ещё «Новая заявка», следующего физического шага нет. | `b02-030-inbound-submitted-detail-locked-1280x720.png` | FAIL_UX | Сотрудник не понимает, закончил ли он работу и что теперь делать с двумя коробами. |
| B02-C035 | Edit/delete/qty controls submitted документа disabled, stock не изменён; лишний Save остаётся активным. | `b02-030...png`, `b02-032...png` | FRICTION | Защита данных работает, но ложная активная кнопка создаёт ненужное действие. |
| B02-C036 | Populated documents содержит submitted inbound, четыре inbound drafts и один MP draft; строки одной даты почти неразличимы и не имеют номера. | `b02-041-documents-normalized-viewport-final-1280x720.png` | FAIL_PROCESS | Единственный рабочий результат тонет среди автоматически созданных документов; высок риск открыть/передать не тот. |
| B02-C037 | Filter «Поставка» не прогнан до settled visible outcome. | Нет собственного screenshot | NOT_RUN | Фильтрация inbound не доказана. |
| B02-C038 | Filter «Отгрузка на МП» не прогнан до settled visible outcome. | Нет собственного screenshot | NOT_RUN | Фильтрация MP не доказана. |
| B02-C039 | Filter «Акт расхождений» не прогнан до settled visible outcome. | Нет собственного screenshot | NOT_RUN | Фильтрация актов не доказана. |
| B02-C040 | Все созданные documents имеют одну дату; сравнить new→old и old→new на двух датах невозможно. | `b02-041...png` | BLOCKED_FIXTURE | Для честной проверки сортировки нужен второй безопасный dated document. |
| B02-C041 | Клик по inbound-row открыл detail с тем же lines/status, но row не показывает ID, поэтому человек не может заранее выбрать точный документ. | `b02-022...png`, `b02-030...png`, `b02-041...png` | FRICTION | Переход работает, идентификация до клика — нет. |
| B02-C042 | Reload detail подтверждён; полный back/forward цикл не снят. | `b02-024...png`, `b02-030...png` | FRICTION | Read-back есть, browser-history recovery покрыт частично. |
| B02-C043 | «Создать акт расхождений» вернул сообщение «будет реализован», реального процесса/документа нет. | `b02-033-discrepancy-cta-placeholder-1280x720.png` | FAIL_PROCESS | Обещанная рабочая операция отсутствует, альтернативный канал не указан. |
| B02-C044 | Double-click/recovery акта не имеют смысла: первая попытка уже заканчивается placeholder. | `b02-033...png` | FAIL_PROCESS | От двойной mutation защищаться нечему; продолжить складской сценарий невозможно. |
| B02-C045 | CTA MP создал один empty seller draft до выбора товара и оставил его после Close. | `b02-035-mp-shipment-create-result-1280x720.png`, `b02-037-mp-shipment-close-leaves-draft-1280x720.png`, `b02-041...png` | FAIL_PROCESS | Close воспринимается как отмена, но оставляет реальный мусорный документ. |
| B02-C046 | Settled MP dialog shell визуально не доказан: `034` transitional, последующие captures показывают список. | `b02-034...png` исключён как invalid evidence | NOT_RUN | Date/warehouse/plan-only hint и Close не получили визуальный verdict. |
| B02-C047 | Picker/wrong qty/cancel нельзя полноценно проверить без available in-cell stock; сам picker на `036` неразличим. | `b02-036-mp-shipment-product-picker-zero-available-1280x720.png`; runtime | BLOCKED_FIXTURE | Нужен изолированный принятый и размещённый stock, а не live/shared stock. |
| B02-C048 | Runtime сообщил zero-available outcome, но PNG не показывает picker/message; available-SKU case отсутствует. | `b02-036...png` | BLOCKED_FIXTURE | Business guard ожидаем, но понятность объяснения и recovery глазами не доказаны. |
| B02-C049 | Save/edit/reload MP plan не выполнены из-за отсутствия available synthetic stock. | Финальный stock=0 на `b02-032...png` | BLOCKED_FIXTURE | Нельзя подменять полноценный populated MP flow пустым draft. |
| B02-C050 | MP row видна, но open/back и тот же draft ID не проверены. | `b02-041...png` | NOT_RUN | Row-level recovery MP не доказан. |
| B02-C051 | Confirm/ship/unplan/cancel/external actions не нажимались по safety; dialog с controls не зафиксирован. | Safety contract; нет собственного screenshot | NOT_RUN | Внешняя отгрузка остаётся за границей B02, положительный verdict не присваивается. |
| B02-C052 | Settings overview показывает WB и ЧЗ cards; capture узкий/malformed. | `b02-039-seller-settings-overview-1280x720.png` | FRICTION | Смысл credentialless state виден, но полноценная 1280 layout-проверка Settings не закрыта. |
| B02-C053 | WB key «не добавлен», sync disabled; key dialog не открывался. | `b02-039...png` | PASS | На Settings граница понятна и безопасна. |
| B02-C054 | ЧЗ summary видна частично, edit не открывался. | `b02-039...png` | NOT_RUN | Поля/validation/cancel нельзя оценить по overview. |
| B02-C055 | Cancel safe non-secret change не выполнялся. | Нет собственного screenshot | NOT_RUN | Нет verdict. |
| B02-C056 | Save safe non-secret field double-click не выполнялся. | Нет собственного screenshot | NOT_RUN | Нет verdict. |
| B02-C057 | Reload/read-back safe setting не выполнялся. | Нет собственного screenshot | NOT_RUN | Нет verdict. |
| B02-C058 | Wrong non-secret input/recovery не выполнялись. | Нет собственного screenshot | NOT_RUN | Нет verdict. |
| B02-C059 | Add/replace key, token entry и sync сознательно не выполнялись. | Safety contract | NOT_RUN | Это безопасный пропуск, а не PASS. |
| B02-C060 | 41 PNG сохранены, нормальный 1280 финальный кадр есть; валидного 1920×1080 DPR1 evidence нет. | `evidence/b02/`; `b02-008...png` invalid, `b02-041...png` authoritative 1280 | NOT_RUN | Двух-viewport gate не закрыт. |
| B02-C061 | Отдельный sanitized state/network log в evidence отсутствует. | В `evidence/b02/` только PNG | NOT_RUN | Runtime-факты есть в slices, но требуемый воспроизводимый журнал не сохранён. |
| B02-C062 | Этот ledger содержит все 63 checklist IDs ровно по одному. | `B02_SCREEN_ACTION_LEDGER_RU.md` | PASS | Ничего не пропущено молча; непроверенное осталось NOT_RUN/BLOCKED_FIXTURE. |
| B02-C063 | Findings и handoff созданы только по подтверждённому evidence. | `B02_FINDINGS_RU.md`, `B02_HANDOFF_RU.md` | PASS | Батч можно передать оркестратору для gate, но не считать продуктовый flow безопасным. |

## Counts и gate

- `PASS`: **9**.
- `FRICTION`: **15**.
- `FAIL_PROCESS`: **6**.
- `FAIL_UX`: **8**.
- `BLOCKED_FIXTURE`: **4**.
- `NOT_RUN`: **21**.

Проверка суммы: `9 + 15 + 6 + 8 + 4 + 21 = 63`.

Формальный gate батча: **`RETURN_FOR_COVERAGE`**. Причина не только в 21 `NOT_RUN` и отсутствующем 1920/state-log evidence: подтверждённый core flow содержит process stop-gates, из-за которых его нельзя безопасно отдавать плохо обученному сотруднику.
