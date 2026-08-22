# Screen development report · 06-picking-list-order · атом 5 · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/fbsApi.ts` — добавлено безопасное отображение кодов ошибок полной ленты на языке склада: только отсутствие PNG называется неполученным стикером.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — печать из открытого листа использует полный серверный снимок `order_ids`, показанный оператору, и превращает конфликт изменившегося состава в требование обновить лист.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx` — полный маршрут показывает ошибки в постоянном порядке, скрывает выборочную печать и поле копий, а физическая лента всегда содержит ровно одну пару `WB → WMS № K` на готовый заказ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx` — прямо названный ревьюером файл того же слоя передаёт в запуск печати полный снимок ID уже загруженного листа и не загружает второй снимок молча.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.test.ts` — добавлена проверка разных складских формулировок для отсутствующего WB-стикера, отсутствующей строки упаковки и ошибки передачи маркировки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts` — добавлены сценарии `S-03-TC-004`, `S-03-TC-005` и `S-03-TC-008`: итоговая кнопка, содержимое открытого окна печати, повторная полная лента, запрет копий/выборочной печати, разные `ErrorNotice` и отказ печатать устаревший лист.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — этот отчёт.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, код 0; финальный прогон выполнен после продуктовых правок.
- `npm run test:unit -- src/screens/v2/FbsPrintPreviewDialog.test.ts src/screens/v2/FfFbsPickList.test.ts src/screens/v2/FfFbsSupplyWorkspace.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, 3 файла и 14 тестов прошли; финальный прогон выполнен после продуктовых правок.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **красный вне границ атома**: baseline сообщает новые нарушения `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`. Эти файлы не менялись. Для `FfFbsPickList.tsx` guard сообщает улучшения: `свой-чип 1 → 0`, `своя-кнопка 2 → 0`, `своя-таблица 1 → 0`; для `FfFbsSupplyWorkspace.tsx` — `экран-монолит 2493 → 2451`. Baseline не обновлялась.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-003|S-03-TC-004 S-03-TC-005|S-03-TC-008'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **красный по среде до запуска кейсов**: Playwright webServer не смог открыть `127.0.0.1:18000`, `[Errno 1] operation not permitted`; тесты не исполнялись.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-003|S-03-TC-004|S-03-TC-005|S-03-TC-008' --list` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, обнаружены 4 целевых сценария в одном файле, включая отдельный сценарий ошибок предпросмотра.
- `npx eslint src/screens/v2/FfFbsPickList.tsx src/screens/v2/FfFbsSupplyWorkspace.tsx src/screens/v2/FbsPrintPreviewDialog.tsx src/screens/v2/fbsApi.ts src/screens/v2/FbsPrintPreviewDialog.test.ts tests-e2e/ff-fbs-supply.spec.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **красный на существующей структуре файлов**: 5 правил `react-refresh/only-export-components` для ранее экспортированных чистых функций в `FbsPrintPreviewDialog.tsx` и `FfFbsPickList.tsx`; новых иных диагностик нет.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **зелёный**, код 0 до записи отчёта.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` после записи отчёта — **зелёный**, код 0.
- `git add -- frontend/src/screens/v2/fbsApi.ts frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx frontend/src/screens/v2/FbsPrintPreviewDialog.tsx frontend/src/screens/v2/FfFbsPickList.tsx frontend/src/screens/v2/FbsPrintPreviewDialog.test.ts frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(fbs): keep picking list tape consistent"` — **не выполнено средой**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock`, `Operation not permitted`. Текущий сохранённый `HEAD` — `a21180bfadacdf0eb8464550a625aa48a3049e77`; он не содержит эту переделку.

## Не реализовано

- Пункты контракта атома 5 реализованы буквально; функциональных пропусков внутри разрешённого слоя нет.
- Находка 1 ревью про регистрацию `FfFbsPickList.tsx` относится к границе атома 6 и `frontend/screens.registry.json`; этот атом реестр не меняет.
- Находка 2 ревью про несовместимые свойства MUI относится к примитивам атома 1 в `frontend/src/ui-kit/`; этот атом их не меняет.
- Живой браузерный результат четырёх сценариев не подтверждён из-за запрета sandbox на локальный порт; это ограничение проверки, а не пропущенная ветка реализации.
- Отдельный Git-коммит атома не создан из-за read-only доступа sandbox к общей Git-метапапке worktree. Изменения находятся в постоянной назначенной рабочей копии, но пока не являются восстанавливаемым Git-результатом.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
- Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md` сохранено без изменений и в коммит атома не включается.
