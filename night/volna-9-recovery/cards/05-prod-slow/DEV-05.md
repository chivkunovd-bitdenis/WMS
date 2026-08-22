# DEV · 05-prod-slow · атом 5 · TableLoadMore

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/TableLoadMore.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/TableLoadMore.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/UiKitShowcase.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/index.ts`
проверен и не изменён: `TableLoadMore` и `TableLoadMoreProps` уже экспортируются из
него буквально по контракту.

`TableLoadMore` скрывается без следующего курсора, показывает одно действие
«Показать ещё», при `loading=true` показывает «Загружаем…» со спиннером и
блокирует кнопку и обработчик, а при ошибке растягивает `ErrorNotice` над вновь
доступной центрированной кнопкой. Showcase явно подписывает все четыре
состояния, включая намеренно отсутствующий скрытый элемент. Добавлен unit-тест
этих состояний.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — **красный** на четырёх
  ранее существующих ошибках вне файлов атома: отсутствующий экспорт
  `beginPrintUserGesture` в `src/components/MarkingPrintDialog.tsx`, неиспользуемый
  `serverNow`, несовместимый `string | null` и запрещанный prop `size` в
  `src/screens/v2/FfFbsOrdersScreen.tsx`. Узкая проверка изменённых файлов через
  `npx tsc --ignoreConfig ... TableLoadMore.tsx TableLoadMore.test.ts UiKitShowcase.tsx`
  — **зелёная**.
- `python3 scripts/ui/ui_guard.py` из корня — **красный** на уже существующих
  превышениях baseline в `MarkingPrintDialog.tsx`, `WbProductPickerDialog.tsx`,
  `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и
  `SellerInboundDraftScreen.tsx`. Файлы этого атома в нарушениях отсутствуют;
  baseline флагом `--update` не менялся.
- `npm run test:unit` из `frontend/` — **зелёный**, 20 файлов и 142 теста. Новый
  адресный набор `src/ui-kit/TableLoadMore.test.ts` — **зелёный**, 4 из 4.
- `git diff --check` — **зелёный**.
- `git add ... && git commit -m "fix(ui-kit): verify table load more states"` —
  **красный до изменения индекса**: Git не смог создать
  `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`,
  `Operation not permitted`. Новый commit SHA не создан.

## Не реализовано

В пределах атома нет пунктов контракта, которые не удалось реализовать
буквально. Сделать два общих гейта зелёными нельзя без правок соседних экранов,
которые запрещены ролью `screen-dev` и не относятся к атому 5; ложное обновление
baseline также запрещено инструкцией роли.

## Находки

`REVIEW.md` не содержит замечаний к файлам или поведению `TableLoadMore` и прямо
подтверждает локальную блокировку двойного клика и доступный повтор после ошибки.
В ходе переделки закрыт отдельный пробел проверки нового ui-kit-примитива:
добавлен собственный unit-тест. Секреты, ключи, токены, `.env`, кабинеты учётных
данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не
затрагивались.

## Блокеры

Атом локально реализован в постоянной рабочей копии, но не сохранён отдельным
Git-коммитом из-за запрета среды на запись в служебный индекс зарегистрированного
worktree. Старый `HEAD` `099602e2` не содержит эту переделку и не является SHA
результата.
