# DEV · 04-warehouse-switch · screen-dev · feature 13

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx` — выбор склада только в новой заявке/черновике при двух и более доступных операционных складах; выбор сохраняется в черновике, после передачи отображается только имя.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/sellerInboundDocumentUi.test.ts` — проверки видимости выбора склада для одного/нескольких складов и статуса черновика.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный: базовая проверка сообщает о существующих нарушениях в других экранах и о росте монолитности `SellerInboundDraftScreen.tsx` из-за реализации в разрешённом экранном файле; baseline не обновлялся.
- `npm run test:unit -- --run src/screens/v2/sellerInboundDocumentUi.test.ts` из `frontend/` — красный до запуска тестов: `vitest: command not found`.

## Не реализовано

- E2E-сценарий в `seller-cabinet.spec.ts` не расширен: браузерный тест-runner зависит от отсутствующего локального `vitest`, а полноценная фикстура с двумя операционными складами требует backend-данных вне разрешённых файлов этого атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.
