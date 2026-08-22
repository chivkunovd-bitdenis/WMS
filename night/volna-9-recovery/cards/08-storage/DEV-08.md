# 08-storage · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

`App.tsx` и `frontend/tests-e2e/storage.spec.ts` в этом проходе не изменялись: маршрут S-11 уже подключён, а существующие тесты не требуют изменения для внесённой экранной правки.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: в `frontend/` отсутствует исполняемый `tsc`, а `npx --no-install` не доступен.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх предсуществующих нарушений вне атома S-11: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit` — не подтверждён: исполняемый `vitest` отсутствует в `frontend/node_modules`.

## Не реализовано

- API-персистентность, реальные тарифы, измерения, расчёт и фиксация не реализованы: находки REVIEW относятся к backend-файлам, которые запрещены границами screen-dev.
- Исправление подписи `PrintAction` «Печать накладной» не внесено: контракт указывает `frontend/src/ui-kit/Actions.tsx`, но этот файл не входит в разрешённый список атома.
- Полное покрытие `S-11-TC-001`—`S-11-TC-020` не расширялось: добавление сценариев, требующих авторизации и backend-состояний, без доступного API было бы недостоверным.
- В экранной логике исправлены только локальные проблемы слоя экрана: поиск учитывает пробелы и пустой запрос, а формирование показывает состояние загрузки и не допускает повторный запуск.

Изменения не удалось закоммитить: Git заблокирован правами окружения на `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`).
