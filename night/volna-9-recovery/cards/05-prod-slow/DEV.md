# DEV · 05-prod-slow · S-03 pagination rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/fbsApi.ts` не менялся: его запрос уже передаёт `limit` и `cursor` по контракту этого атома.

Фоновый 30-секундный тик теперь явно отделён от обычной загрузки: он заменяет только первую порцию, сохраняет реально догруженный хвост и удаляет устаревшие строки именно из первой порции. Смена селлера, склада или вкладки выполняет обычную замену списка и не смешивает выдачи. Устаревший ответ отменяется номером запроса. Пустое состояние остальных вкладок снова использует их общий текст, а не текст вкладки «Новые».

В E2E добавлены/уточнены сценарии `S-03-TC-001`–`S-03-TC-007` и `S-03-TC-010`–`S-03-TC-012`: 50 строк, догрузка, «Выбрать все» по курсорам, скелет, пустой ответ, фоновый тик, лимит 100 на рабочей вкладке, двойной клик, ошибка с повтором и скрытая вкладка.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`) — зелёный.
- `npm run test:unit` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный. Скрипт сообщает новые нарушения монолитности в `src/components/MarkingPrintDialog.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Baseline через `--update` не менялась; три из пяти файлов не входят в разрешённую границу этого атома.
- `npm run test:e2e -- tests-e2e/ff-fbs-orders.spec.ts` — не запущен: в локальном `frontend/node_modules` нет `playwright`; npm вызвал постороннюю команду `playwright`, которая вернула `error: unknown command 'test'`.

## Не реализовано

- Браузерный прогон новых `S-03` сценариев не подтверждён из-за отсутствующего локального Playwright. Сами сценарии записаны в разрешённый E2E-файл.
- Зелёный `ui_guard.py` не получен: исправление остальных четырёх указанных скриптом файлов либо изменение baseline запрещены границей роли и атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.
