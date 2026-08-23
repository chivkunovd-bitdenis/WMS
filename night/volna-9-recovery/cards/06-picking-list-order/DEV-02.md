# DEV · 06-picking-list-order · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Actions.tsx` — у `PrintAction` для состояния подготовки убран обработчик нажатия; повторно запустить печать нельзя и программной передачей события.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/PickingListPrimitives.test.ts` — добавлены точные проверки aria-подписи `CheckCell`, переключения отметки, причины блокировки, подписи «Печать стикеров», текста подготовки и отсутствия повторного обработчика во время подготовки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — артефакт роли.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Cells.tsx` проверен: требуемые `CheckCell`, aria-подпись и пояснение недоступного состояния уже реализованы буквально, поэтому правка этого файла не потребовалась.

## Гейты

- КРАСНЫЙ, зависимости отсутствуют: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx tsc --noEmit -p tsconfig.app.json` не смог запустить TypeScript. Локального `tsc` нет; `npx` попытался получить пакет из `https://registry.npmjs.org/tsc` и завершился `ENOTFOUND` из-за недоступной сети.
- КРАСНЫЙ, внешние по отношению к атому прежние нарушения: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && python3 scripts/ui/ui_guard.py` сообщил только `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/components/WbProductPickerDialog.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Они не входят в атом и не менялись; базовая линия не обновлялась.
- КРАСНЫЙ, зависимости отсутствуют: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npm run test:unit -- src/ui-kit/PickingListPrimitives.test.ts` не стартовал: `sh: vitest: command not found`.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && git diff --check`.
- Полные backend-проверки, `ruff` и `mypy` не запускались: они прямо запрещены ограничением атомарной проверки.

## Не реализовано

Все пункты контракта атома 2 реализованы. Находка `JUDGE.md` относится к живому browser-review и снимкам всего S-03, а не к разрешённому ui-kit-слою; выполнить её в этой роли и этими файлами невозможно.

## Находки

- `JUDGE.md` не называет дефектов в `CheckCell` или `PrintAction`; единственная находка — отсутствие живого стенда и снимков `S-03-TC-001`…`S-03-TC-013`.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
