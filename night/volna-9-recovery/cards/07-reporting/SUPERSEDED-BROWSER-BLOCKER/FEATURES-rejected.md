ФИЧ: 3

## Фичи

### 1. Общая полоса показателей отчёта

Оператор видит четыре связанных показателя в одной компактной полосе: текущий остаток, приход, расход и изменение расхода. Нулевое значение остаётся числом, неприменимое сравнение показано тире с пояснением, а при обновлении вместо прежних чисел видны скелеты. Это отдельный ui-kit-атом, который должен быть создан и проверен до экранной части отчёта; сам маршрут и экран в этом атоме не меняются.

Файлы продукта:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.tsx`

Проверка:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.test.tsx` проверяет обычные, нулевые, неприменимые и loading-состояния, включая доступную подпись изменения.

Зависимости: нет.

### 2. Общий график входящего и исходящего потока

Оператор видит на графике подписанные серии «Приход» и «Расход», а при включённом сравнении — отдельно различимую пунктирную серию прошлого периода. Если движений нет, график честно объясняет пустой результат, а во время обновления показывает скелет. Это отдельный ui-kit-атом: он не меняет фильтры, API или экран отчёта.

Файлы продукта:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx`

Проверка:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx` проверяет легенду, отсутствие сравнения, пустое состояние, скелет и текстовое описание серий.

Зависимости: нет.

### 3. Предупреждение уровня всего отчёта

Оператор ФФ получает одну заметную плашку предупреждения о неполных внешних или восстановленных исторических данных, без чипов в каждой строке. Элемент остаётся парным `ErrorNotice` и не добавляет права, фильтры или маршруты. Это последний ui-kit-атом, после которого экран может использовать все три недостающих общих элемента.

Файлы продукта:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.tsx`

Проверка:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx` проверяет `Alert` с уровнем `warning`, текстом и стабильным `testId`.

Зависимости: нет.

## Порядок

1. Сначала выполнить атом 1: это первый frontend-атом и отдельное создание `ReportMetricStrip` в ui-kit, как требует контракт.
2. Атомы 2 и 3 независимы от атома 1 и друг от друга; их можно выполнять параллельно с ним. Все три ui-kit-атома должны быть завершены до любой новой экранной работы.
3. Экран `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` и его e2e уже приняты и в это перепланирование не возвращаются. После наличия живого браузера их следует только повторно принять по `S-33-TC-001`–`S-33-TC-007`; это приёмка, не новый атом разработки.

## Что осталось за бортом

- Исправление среды, которая не даёт поднять локальный стенд на `127.0.0.1:18000`, и предоставление живого браузера: это причина незакрытого verdict из `JUDGE.md`, но не изменение backend- или frontend-продукта.
- Повторная разработка `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`, API и моделей отчёта: эти границы уже приняты, поэтому расширять карточку ими нельзя.
- Деньги, хранение, счета, продажи и отдельный финансовый отчёт селлера: они исключены контрактом и `ARCH-CROSS.md` относит их к карточкам 08/09.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
