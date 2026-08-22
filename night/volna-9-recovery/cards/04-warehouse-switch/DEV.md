# DEV · 04-warehouse-switch · атом 7 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/InboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/OutboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/inbound-intake.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/outbound-submit-storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

На S-22 и S-24 `WarehouseContextSwitch` вынесен из левой колонки в отдельную
строку сразу под заголовком и до всей зависимой области экрана. При открытом
документе строка показывает склад документа и блокирует смену. Сам документ также
показывает имя своего склада текстом; технический ID в интерфейс не выводится.

Действие `К списку` очищает только открытый документ, поэтому переключатель снова
показывает сохранённый склад сессии. Вторые поля `Склад для заявки` и `Склад для
отгрузки` отсутствуют. При одном операционном складе общий переключатель не
рендерится, как требует контракт.

E2E-сценарии дополнены проверкой двух разных складов: оператор выбирает южный склад,
открывает исторический документ северного склада, видит его склад, возвращается к
списку и снова видит южный сессионный контекст. Новый документ сохраняет южный склад,
а список ячеек приёмки не содержит ячейку северного склада.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — красный до проверки
  файлов атома: соседний `src/screens/v2/FbsSupplyCreateDialog.test.ts` содержит JSX
  в файле `.ts`, поэтому TypeScript останавливается на синтаксических ошибках строки
  55. Этот файл не входит в разрешённый слой атома 7.
- `python3 scripts/ui/ui_guard.py` из корня — красный только на накопленных
  отклонениях соседних файлов: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`,
  `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и
  `SellerInboundDraftScreen.tsx`. Для затронутого `InboundScreen.tsx` guard показывает
  улучшение `экран-монолит 691 → 690`; нового нарушения атом не добавляет. Базовая
  линия не обновлялась.
- `npm run test:unit` из `frontend/` — красный на том же соседнем
  `FbsSupplyCreateDialog.test.ts`; остальные 20 файлов и 150 unit-тестов зелёные.
- `npx eslint src/screens/v2/InboundScreen.tsx src/screens/v2/OutboundScreen.tsx tests-e2e/inbound-intake.spec.ts tests-e2e/outbound-submit-storage.spec.ts` — зелёный.
- `npx playwright test tests-e2e/inbound-intake.spec.ts tests-e2e/outbound-submit-storage.spec.ts --list` — зелёный: обнаружены 2 сценария в 2 файлах.
- Живой запуск тех же двух Playwright-сценариев — заблокирован до выполнения тестов:
  sandbox не разрешил backend привязать `127.0.0.1:18000` (`operation not permitted`).
- `git diff --check` — зелёный.
- `git add` / отдельный commit — красный: sandbox не разрешил создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`
  (`Operation not permitted`). Восстановимого commit SHA для этого rework нет.

## Не реализовано

- Буквально реализованы все пункты контракта атома 7 в разрешённом экранном слое.
- Полный зелёный результат трёх обязательных гейтов недоступен из-за соседнего
  синтаксически неверного теста, накопленной общей baseline UI-guard и запрета среды
  на локальный порт. Эти соседние файлы и baseline не изменялись.
- Живое прохождение двух Playwright-сценариев не выполнено, потому что тестовый сервер
  не смог стартовать в sandbox; сами сценарии успешно разбираются Playwright.
- Результат локально реализован, но не сохранён в Git из-за запрета записи в служебный
  каталог worktree. Изменения остаются незакоммиченным diff.

## Находки

- Находок о данных, персональных данных или утечках в разрешённом слое атома нет.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
