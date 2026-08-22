ВЕРДИКТ: НАХОДКИ 3

# Code Review · 07-reporting · повторный проход

Вердикт: **CHANGES_REQUESTED**.

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx:187` — `retryOverview()` прерывает общий `abortRef`, которым запущены и сводка, и таблица из `load()`. Сценарий: overview быстро отвечает 503, таблица ещё загружается, оператор нажимает «Повторить»; повтор отменяет успешный табличный запрос, а `load()` из-за отмены не сбрасывает `loading`, поэтому экран остаётся в скелетах даже после успеха повтора. Цена — не закрыты замороженный пункт 8 прошлого review, `S-33-TC-012` и контракт частичного отказа. Новый Playwright-тест этого не ловит: табличный mock отвечает до нажатия retry.

2. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx:39`, `:84` и `:91` — frontend фактически не собирается: текущие MUI-типы не принимают `alignItems`/`flexWrap` как прямые props у `Stack` и `fontWeight` как прямой prop у `Typography`. Сценарий: CI или сборка стенда запускают `npm run build` и падают с `TS2769` до сборки Vite. Цена — карточку нельзя собрать и поставить. Это пропуск первого review, вынесенный в повторном проходе по явному исключению роли для реально непроходящей сборки.

3. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.test.tsx:1`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx:1`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.test.tsx:1` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx:1` — все целевые unit-тесты имеют расширение `.test.tsx`, но `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/vitest.config.ts:6` ищет только `src/**/*.test.ts`. Сценарий: `npm run test:unit` зелёный на 138 старых тестах, но не запускает ни одной из этих четырёх спецификаций; прямой запуск тех же путей завершается `No test files found`. Цена — фильтр операционных складов, график, метрики и `WarningNotice` фактически не защищены заявленными тестами.

## Проверено и нормально

- Проверено закрытие всех 10 пунктов замороженного `REVIEW.md` и ремонтный diff после него. Пункты 1–7, 9 и 10 закрыты; пункт 8 о независимом retry остался дефектным в гонке с медленной таблицей.
- Московские полуинтервалы, декабрьская граница года, нулевые дни графика, формат warnings, состав transfer-пары и русские названия операций реализованы в соответствии с контрактом.
- Область seller принудительно задаётся на backend; служебные `FBS WB *` склады исключены из обычного среза; CSV повторяет фильтры, группировку и сортировку таблицы.
- Backend-проверка: `14 passed in 12.35s`; `git diff --check` зелёный. Frontend unit-run зелёный только для 19 обнаруженных `.test.ts`-файлов (`138 passed`); целевые `.test.tsx` не запускались, а frontend build падает, как указано выше.

Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
