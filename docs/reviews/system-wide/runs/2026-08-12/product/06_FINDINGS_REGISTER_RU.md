# Реестр продуктовых findings

## Подтверждённые findings

### PROD-001 — P1 — Инвентаризация является тупиком из основного меню

В FF sidebar есть полноценный пункт `Инвентаризация`. Реальный клик на staging открывает экран только с `Раздел в разработке`, без создания задания, выбора охвата, пересчёта, фиксации расхождений или проводки. Для администратора это не «пустое состояние», а обещанный основной складской процесс, который не существует. Static route подтверждает тот же placeholder.

Риск: склад не может выполнить и документально закрыть пересчёт в системе; пользователь вынужден уйти во внешние таблицы или править остатки косвенными операциями.

Evidence: `UI-FF-INVENTORY__synthetic-admin__1280x720__clicked.png`, лично просмотрен product reviewer.

### PROD-003 — P2 — Dashboard показывает оператору внутренний статус `submitted`

На реальном staging screenshot в блоке запланированных отгрузок виден текст `Статус «submitted»`. Это внутреннее имя состояния API, а не складской язык. Рядом уже есть русское пояснение, поэтому технический token не помогает принять решение и добавляет визуальный шум.

Риск: сотрудник не понимает, готов ли документ к сборке/отгрузке, и начинает сверяться с разработчиками или запоминать внутренние коды.

Evidence: `UI-FF-DASHBOARD__synthetic-admin__1280x720__clicked.png`, лично просмотрен.

### PROD-004 — P1 security handoff — Release signing keystore хранится в Git как обычный читаемый файл

`mobile/android/wms-tsd-release.jks` отслеживается Git с mode `100644` и на файловой системе доступен как `-rw-r--r--`; release build config ссылается на этот файл. Ключ не использовался, не открывался через keytool и не экспортировался.

Риск: любой читатель репозитория/его копии получает сам signing artifact и при наличии пароля может выпускать APK, выглядящий доверенным для устройств. Это cross-cutting security finding, переданный security review; секретные значения и fingerprint в отчёт не включены.

Evidence: read-only Git index/history и filesystem metadata mobile repo.

### PROD-005 — P1 — Seller action «Акт расхождений» фактически заглушен ошибкой «будет реализован»

Оркестратор реально нажал seller CTA на staging. Вместо создания документа экран показал error alert: акт расхождений будет реализован на следующем этапе. Действие присутствует в пользовательском контуре, но не имеет бизнес-результата.

Риск: селлер не может формально отработать несоответствие и вынужден использовать внешний канал; склад и seller теряют единый след решения.

Evidence: `UI-SELLER-DOCUMENTS__discrepancy-action__1920x1080__clicked.png`, лично просмотрен product reviewer; static handler согласуется с результатом.

### PROD-006 — P1 — Один checkbox необратимо размывает адресные остатки без предупреждения до действия

На реальном Settings screen виден обычный checkbox `Адресное хранение включено`. Его handler сразу отправляет изменение; при переходе `true → false` backend атомарно переносит все ненулевые остатки со всех адресных ячеек в виртуальную `Сортировку`. Действующий DEC-019 отдельно говорит, что при обратном включении автоматического возврата по прежним ячейкам нет. Пользователь узнаёт о переносе только после успеха.

Риск: случайный клик администратора уничтожает полезную адресную детализацию всего склада и превращает последующее восстановление в ручную раскладку/пересканирование. Проверять mutation на staging не стали именно потому, что это массовая операция с остатками.

Минимальное исправление: перед выключением показать отдельное подтверждение простым текстом — все остатки уйдут в `Сортировку`, автоматического возврата не будет — и требовать второй осознанный клик. Не нужен новый процесс или экран.

Evidence: лично просмотренные `UI-FF-SETTINGS__synthetic-admin__1280x720__clicked.png` и `UI-FF-SETTINGS__synthetic-admin__1920x1080__stable-2s.png`; static request/backend effect на baseline `a39530c`.

## Кандидаты, которые нельзя повысить без следующего evidence

`Забрать заказы из WB` на FBS empty screen отдельно не считается finding: самый новый утверждённый эталон прямо фиксирует экран `Заказы FBS` как проверенный и запрещает его менять. Более старое требование автоматического polling относится к статусам активных поставок и не даёт основания самовольно удалить manual intake action с экрана заказов.

### PROD-C01 — FBS packing actions `ТЗ`, `QR` и icon-only print короче утверждённых названий

Static source показывает `ТЗ`, `QR` и printer icon, тогда как утверждённый baseline требует явные `ТЗ на упаковку`, `Печать QR`, `Печать`. Это может заставить нового упаковщика угадывать назначение соседних print actions. Нужен populated packing screenshot в 1280×720 и реальное открытие каждого диалога.

### PROD-C02 — Mobile inbound «печать» может только отмечать факт, не печатая физическую этикетку

На static mobile screen printer icon вызывает `markLabelPrinted`. Без device/printer runtime не доказано, что печать инициируется другим слоем. До такого прогона процесс печати внутреннего ШК коробов нельзя считать закрытым.

### PROD-C03 — Catalog перегружен 14 колонками и техническим `WB nm`

На 1280×720 заголовки уже переносятся в 2–3 строки. `WB nm` не расшифрован. Нужен populated screenshot и проверка horizontal overflow/поиска, прежде чем считать это доказанным лишним трудом.

### PROD-C04 — FBS packing summary добавляет общий счётчик `Напечатано … · упаковано …`

Static UI выводит общий progress summary, хотя утверждённый минимальный baseline делает факт печати свойством строки (приглушение + check) и запрещает лишние статусы/чипы. На populated screenshot нужно проверить, помогает ли summary контролировать партию или дублирует строки и отвлекает.

### PROD-C05 — Полноценный billing flow не найден

Есть расчётный месяц и ставки сотрудников, но отдельный маршрут начислений/счетов/проводок для seller и FF в фактическом route inventory не найден. Требуется связать ожидание с действующим утверждённым billing contract; до этого это scope gap candidate, а не придуманная функция.

### PROD-C06 — Dashboard callback MP-строки строит лишний сегмент `/ff`

Baseline source `a39530c` формирует из `base=/app/ff` путь ``${base}/ff/mp-shipments``. Статически это `/app/ff/ff/mp-shipments`, которого нет в route inventory. Однако synthetic dashboard не имел строки для реального click, а staging развернут из другой revision `44fe72e`. Поэтому это не runtime finding, а точный static candidate до Browser reproduction на populated dashboard эталонной версии.

### PROD-C07 — Действующий дизайн обещает ЧЗ FF-staff, но фактический access оставляет только admin

Дизайн `Честный Знак` говорит, что список пулов видят FF-admin и FF-staff по всем seller. В baseline sidebar показывает пункт только admin, а marking API разрешает общий scope только `fulfillment_admin` и seller; staff получает `403`. Это может отрезать упаковщика/старшего смены от просмотра остатков КМ. Без отдельной staff credential и screenshot фактического отказа состояние остаётся `STATIC_CONTRACT_MISMATCH`, не runtime FAIL.

## Ограничения evidence, не являющиеся дефектами приложения

### EVID-001 — Staging revision доказана, но не совпадает с эталоном; worker/schema gate неполон

Railway metadata доказывает deployed revision `44fe72e` для доступного web/API deployment, тогда как runtime-эталон ревью — `a39530c`. Отдельный worker deployment в staging отсутствует, schema revision напрямую не опубликована и только выводится косвенно. Поэтому Browser findings относятся к staging `44fe72e`, static candidates — к `a39530c`; их нельзя склеивать без отдельного reproduction.

### EVID-002 — Первый screenshot batch имеет непоследовательное capture-state

При одинаковой подписи 1280×720 часть экранов снята в нормальном desktop layout, часть крупнее, часть в узкой полосе с тёмными gutter’ами. Layout findings по transitional-файлам не выносятся. Stable 1920×1080 batch с `innerWidth=1920`, `innerHeight=1080`, `DPR=1` закрывает второй desktop viewport.

### EVID-003 — Synthetic tenant пуст, а read-only API dataset относится к другому scope

Нельзя соединять empty UI synthetic tenant и populated API другого tenant в ложный end-to-end PASS.

### EVID-004 — Seller пройден частично, mobile runtime не пройден

Seller portal пройден по четырём основным routes в stable desktop viewport; выполнены discrepancy CTA и сохранение inbound draft. Product sync, ЧЗ actions, submit inbound, MP plan и notifications ещё `NOT_RUN`. Mobile static snapshot dirty и без device screenshots; все его экраны `NOT_RUN`.
